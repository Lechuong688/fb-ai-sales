import json

from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError

from backend.database.db import Base, SessionLocal, engine
from backend.database.models.lead import Lead, utc_now
from backend.utils.text_matching import normalize_text


WORKFLOW_STATUSES = {
    "new": "Mới", "contacting": "Đang tư vấn", "follow_up": "Cần theo dõi",
    "won": "Đã chốt", "ignored": "Bỏ qua",
}
REVIEW_STATUSES = {"pending": "Chờ duyệt", "approved": "Đã duyệt trên máy", "rejected": "Không dùng bản nháp"}


class LeadConflict(ValueError):
    pass


def search_text(values):
    text = normalize_text(" ".join(str(values.get(key) or "") for key in (
        "author", "post_text", "post_url", "source_name", "product_label", "skus_json", "notes", "profiles_json",
    )))
    codes = json.loads(values.get("skus_json") or "[]")
    return text + " " + " ".join(normalize_text(code).replace(" ", "") for code in codes)


def serialize(lead):
    values = {column.name: getattr(lead, column.name) for column in Lead.__table__.columns}
    values["skus"] = json.loads(values.pop("skus_json"))
    values["profiles"] = json.loads(values.pop("profiles_json"))
    return values


class LeadRepository:
    def __init__(self, db_engine=None, session_factory=None):
        self.engine = db_engine or engine
        self.session_factory = session_factory or SessionLocal
        Base.metadata.create_all(self.engine, tables=[Lead.__table__])

    def capture(self, profile, records):
        if not records:
            return dict(created=0, updated=0, saved=0)
        for attempt in range(3):
            try:
                return self._capture_once(profile, records)
            except (LeadConflict, IntegrityError):
                if attempt == 2:
                    raise

    def _capture_once(self, profile, records):
        now = utc_now()
        created = updated = 0
        with self.session_factory() as db, db.begin():
            existing = {lead.post_url: lead for lead in db.scalars(select(Lead).where(
                Lead.post_url.in_([record["post_url"] for record in records])
            ))}
            for record in records:
                previous = existing.get(record["post_url"])
                values = dict(record, last_seen=now)
                if previous is None:
                    values.update(
                        profiles_json=json.dumps([profile], ensure_ascii=False),
                        draft_comment=record["suggested_comment"], draft_origin="generated", notes="",
                        workflow_status="new", review_status="pending", version=1, first_seen=now,
                    )
                    values["search_text"] = search_text(values)
                    db.add(Lead(**values))
                    created += 1
                    continue
                profiles = list(dict.fromkeys(json.loads(previous.profiles_json) + [profile]))
                values["profiles_json"] = json.dumps(profiles, ensure_ascii=False)
                changed_context = any(getattr(previous, key) != record[key] for key in (
                    "post_text", "product_label", "skus_json", "suggested_comment", "requires_manual",
                ))
                if previous.draft_origin == "generated":
                    values["draft_comment"] = record["suggested_comment"]
                if changed_context:
                    values["review_status"] = "pending"
                values["version"] = previous.version + 1
                values["search_text"] = search_text(dict(serialize(previous), **values))
                # Preserve notes, workflow state and manually edited replies.
                result = db.execute(update(Lead).where(
                    Lead.id == previous.id, Lead.version == previous.version,
                ).values(**values).execution_options(synchronize_session=False))
                if result.rowcount != 1:
                    raise LeadConflict("Hồ sơ vừa được cập nhật; vui lòng tải lại.")
                updated += 1
        return dict(created=created, updated=updated, saved=created + updated)

    def get(self, lead_id):
        with self.session_factory() as db:
            lead = db.get(Lead, lead_id)
            return serialize(lead) if lead else None

    def get_by_url(self, url):
        with self.session_factory() as db:
            lead = db.scalar(select(Lead).where(Lead.post_url == url))
            return serialize(lead) if lead else None

    @staticmethod
    def _filtered(query="", status="", review=""):
        statement = select(Lead)
        if query.strip():
            term = normalize_text(query)
            if term:
                statement = statement.where(Lead.search_text.contains(term, autoescape=True))
        if status:
            if status not in WORKFLOW_STATUSES:
                raise ValueError("Trạng thái khách hàng không hợp lệ.")
            statement = statement.where(Lead.workflow_status == status)
        if review:
            if review not in REVIEW_STATUSES:
                raise ValueError("Trạng thái duyệt không hợp lệ.")
            statement = statement.where(Lead.review_status == review)
        return statement

    def list(self, query="", status="", review="", offset=0, limit=100):
        statement = self._filtered(query, status, review)
        with self.session_factory() as db:
            total = db.scalar(select(func.count()).select_from(statement.subquery()))
            statement = statement.order_by(Lead.last_seen.desc(), Lead.id.desc()).offset(max(0, offset))
            if limit is not None:
                statement = statement.limit(max(1, min(limit, 500)))
            return dict(total=total, records=[serialize(lead) for lead in db.scalars(statement)])

    def summary(self):
        with self.session_factory() as db:
            return dict(
                total=db.scalar(select(func.count()).select_from(Lead)),
                approved=db.scalar(select(func.count()).select_from(Lead).where(Lead.review_status == "approved")),
                follow_up=db.scalar(select(func.count()).select_from(Lead).where(Lead.workflow_status == "follow_up")),
            )

    def save_review(self, lead_id, version, comment, notes, status, action="save"):
        if status not in WORKFLOW_STATUSES or action not in {"save", "approve", "reject"}:
            raise ValueError("Trạng thái hoặc thao tác không hợp lệ.")
        comment, notes = str(comment).strip(), str(notes).strip()
        if action == "approve" and not comment:
            raise ValueError("Nhập nội dung trước khi duyệt bản nháp.")
        with self.session_factory() as db, db.begin():
            lead = db.get(Lead, lead_id)
            if lead is None:
                raise ValueError("Không tìm thấy hồ sơ khách hàng.")
            if lead.version != version:
                raise LeadConflict("Hồ sơ vừa được cập nhật. Bản đang sửa được giữ nguyên; hãy chép nội dung cần giữ rồi bấm Hoàn tác / Nạp lại để đối chiếu.")
            changed = comment != lead.draft_comment
            review = "approved" if action == "approve" else "rejected" if action == "reject" else "pending" if changed else lead.review_status
            values = dict(draft_comment=comment, notes=notes, workflow_status=status,
                          review_status=review, version=version + 1)
            if changed:
                values["draft_origin"] = "manual"
            values["search_text"] = search_text(dict(serialize(lead), skus_json=json.dumps(json.loads(lead.skus_json)),
                                                     profiles_json=lead.profiles_json, **values))
            result = db.execute(update(Lead).where(Lead.id == lead_id, Lead.version == version).values(**values))
            if result.rowcount != 1:
                raise LeadConflict("Hồ sơ vừa được cập nhật; vui lòng tải lại.")
        return self.get(lead_id)
