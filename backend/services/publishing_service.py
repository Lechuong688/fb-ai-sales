"""Local group collections, reusable content and publishing receipts."""
import json
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, select

from backend.database.db import engine


metadata = MetaData()
collections = Table(
    "publishing_collections", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String, nullable=False),
    Column("profile", String, nullable=False),
    Column("urls", Text, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)
templates = Table(
    "publishing_templates", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String, nullable=False),
    Column("content", Text, nullable=False),
    Column("media", Text, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)
receipts = Table(
    "publishing_receipts", metadata,
    Column("id", Integer, primary_key=True),
    Column("profile", String, nullable=False),
    Column("target", Text, nullable=False),
    Column("kind", String, nullable=False),
    Column("status", String, nullable=False),
    Column("message", Text, nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at", DateTime, nullable=False),
)


class PublishingService:
    def __init__(self, bind=None):
        self.engine = bind if bind is not None else engine
        metadata.create_all(self.engine)

    def list_collections(self, profile=None):
        query = select(collections).order_by(collections.c.name, collections.c.id)
        if profile is not None:
            query = query.where(collections.c.profile == profile)
        with self.engine.connect() as db:
            return [dict(row) | {"urls": json.loads(row["urls"])}
                    for row in db.execute(query).mappings()]

    def save_collection(self, name, profile, urls):
        name, profile = name.strip(), profile.strip()
        urls = sorted(set(urls))
        if not name or not profile or not urls:
            raise ValueError("Nhập tên bộ sưu tập và chọn ít nhất một nhóm của nick.")
        # A named collection belongs to one profile; updating never leaks groups to another.
        with self.engine.begin() as db:
            current = db.execute(select(collections.c.id).where(
                collections.c.name == name, collections.c.profile == profile
            )).scalar()
            values = dict(name=name, profile=profile, urls=json.dumps(urls), updated_at=datetime.now())
            if current is not None:
                db.execute(collections.update().where(collections.c.id == current).values(**values))
                return current
            return db.execute(collections.insert().values(**values)).inserted_primary_key[0]

    def list_templates(self):
        with self.engine.connect() as db:
            return [dict(row) | {"media": json.loads(row["media"])} for row in db.execute(
                select(templates).order_by(templates.c.updated_at.desc(), templates.c.id.desc())
            ).mappings()]

    def save_template(self, name, content, media=()):
        if not name.strip() or not (content.strip() or media):
            raise ValueError("Nhập tên mẫu và nội dung hoặc ảnh/video.")
        with self.engine.begin() as db:
            return db.execute(templates.insert().values(
                name=name.strip(), content=content.strip(), media=json.dumps(list(media), ensure_ascii=False),
                updated_at=datetime.now(),
            )).inserted_primary_key[0]

    def delete(self, category, record_id):
        table = {"collections": collections, "templates": templates}[category]
        with self.engine.begin() as db:
            db.execute(table.delete().where(table.c.id == record_id))

    def record(self, profile, outcomes, content):
        rows = [dict(
            profile=profile, target=str(item.get("target", "")), kind=item.get("kind", "group"),
            status=("submitted" if item.get("success") else item.get("status", "failed")),
            message=str(item.get("message", "")), content=content, created_at=datetime.now(),
        ) for item in outcomes]
        if rows:
            with self.engine.begin() as db:
                db.execute(receipts.insert(), rows)

    def history(self):
        with self.engine.connect() as db:
            return [dict(row) for row in db.execute(
                select(receipts).order_by(receipts.c.created_at.desc(), receipts.c.id.desc())
            ).mappings()]
