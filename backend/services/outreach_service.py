"""Persistent audiences, reviewed outreach schedules and daily activity receipts."""
import hashlib
import json
import re
import string
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from sqlalchemy import (Boolean, Column, Index, Integer, MetaData, String, Table, Text,
                        UniqueConstraint, func, select)

from backend.database.db import engine
from backend.facebook.parsers.group_parser import normalize_group_url
from backend.facebook.parsers.post_date import VIETNAM_TZ
from backend.services.lead_service import real_post_url
from backend.utils.text_matching import normalize_text


ACTIONS = {'join_group': 'Tham gia nhóm', 'group_post': 'Đăng bài nhóm',
           'add_friend': 'Kết bạn', 'engage': 'Tương tác bài mới', 'message': 'Nhắn tin'}
JOB_STATUSES = {'queued': 'Chờ lịch', 'running': 'Đang chạy', 'paused': 'Tạm dừng',
                'done': 'Hoàn tất', 'failed': 'Lỗi', 'review': 'Cần kiểm tra', 'cancelled': 'Đã hủy'}
RESULT_STATUSES = {'running': 'Đang xử lý', 'submitted': 'Đã gửi bài', 'sent': 'Đã gửi tin',
                   'pending': 'Đã gửi yêu cầu', 'done': 'Đã thực hiện', 'skipped': 'Không cần thực hiện',
                   'failed': 'Lỗi', 'review': 'Cần kiểm tra', 'cancelled': 'Đã dừng'}
metadata = MetaData()
settings = Table('outreach_settings', metadata,
    Column('key', String, primary_key=True), Column('enabled', Boolean, nullable=False))
audiences = Table('outreach_audiences', metadata,
    Column('id', Integer, primary_key=True), Column('profile', String, nullable=False),
    Column('kind', String, nullable=False), Column('url', Text, nullable=False),
    Column('name', Text, nullable=False), Column('industry', Text, default=''),
    Column('region', Text, default=''), Column('description', Text, default=''),
    Column('joined', Boolean, default=False), Column('updated_at', String, nullable=False),
    UniqueConstraint('profile', 'kind', 'url'))
jobs = Table('outreach_jobs', metadata,
    Column('id', Integer, primary_key=True), Column('campaign', Text, nullable=False),
    Column('profile', String, nullable=False), Column('action', String, nullable=False),
    Column('target', Text, nullable=False), Column('name', Text, nullable=False),
    Column('content', Text, default=''), Column('media_json', Text, default='[]'),
    Column('next_at', String, nullable=False), Column('repeat_days', Integer, default=0),
    Column('daily_limit', Integer, default=20), Column('gap_seconds', Integer, default=60),
    Column('status', String, nullable=False), Column('token', String, default=''),
    Column('started_at', String, default=''), Column('cancel_requested', Boolean, default=False),
    Column('last_message', Text, default=''), Column('fingerprint', String, nullable=False))
activity = Table('outreach_activity', metadata,
    Column('id', Integer, primary_key=True), Column('job_id', Integer, nullable=False),
    Column('token', String, nullable=False, unique=True), Column('profile', String, nullable=False),
    Column('action', String, nullable=False), Column('target', Text, nullable=False),
    Column('name', Text, nullable=False), Column('content', Text, default=''),
    Column('status', String, nullable=False), Column('message', Text, default=''),
    Column('created_at', String, nullable=False), Column('finished_at', String, default=''))
Index('ix_outreach_jobs_due', jobs.c.status, jobs.c.next_at)
Index('ix_outreach_jobs_profile', jobs.c.profile, jobs.c.status)
Index('ix_outreach_jobs_fingerprint', jobs.c.fingerprint)
Index('ix_outreach_activity_day', activity.c.profile, activity.c.action, activity.c.created_at)


def local_now():
    return datetime.now(VIETNAM_TZ)


def timestamp(value):
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError('Thời gian cần có múi giờ.')
    return value.astimezone(VIETNAM_TZ).isoformat(timespec='seconds')


def normalize_target(kind, value):
    if kind == 'group':
        return normalize_group_url(value)
    if kind == 'post':
        result = real_post_url(value)
        if not result or {'comment_id', 'reply_comment_id'} & parse_qs(urlparse(result).query).keys():
            raise ValueError('Dùng link bài viết, không dùng link bình luận.')
        return result
    parsed = urlparse(str(value or '').strip())
    if (parsed.scheme not in {'https', 'http'} or parsed.username is not None or parsed.password is not None
            or parsed.port not in {None, 80, 443}
            or parsed.hostname not in {'www.facebook.com', 'facebook.com', 'm.facebook.com', 'messenger.com', 'www.messenger.com'}):
        raise ValueError('Dùng link Facebook hoặc cuộc trò chuyện Messenger hợp lệ.')
    path = parsed.path.strip('/')
    if kind == 'thread':
        match = re.fullmatch(r'(?:messages/)?(e2ee/)?t/(\d+)', path)
        if not match:
            raise ValueError('Link hội thoại cần có dạng facebook.com/messages/t/123 hoặc messenger.com/t/123.')
        return f'https://www.facebook.com/messages/{match[1] or ""}t/{match[2]}/'
    if kind != 'person' or 'messenger.com' in parsed.hostname:
        raise ValueError('Loại đối tượng không hợp lệ.')
    if path == 'profile.php':
        uid = (parse_qs(parsed.query).get('id') or [''])[0]
        if not uid.isdigit():
            raise ValueError('Link cá nhân cần UID hợp lệ.')
        return f'https://www.facebook.com/profile.php?id={uid}'
    reserved = {'groups', 'search', 'watch', 'reel', 'reels', 'marketplace', 'messages', 'friends',
                'login', 'login.php', 'checkpoint', 'home.php', 'settings', 'notifications', 'share',
                'photo', 'photos', 'photo.php', 'pages', 'events', 'gaming', 'help', 'privacy', 'policies',
                'recover', 'about', 'videos', 'me'}
    if not re.fullmatch(r'[A-Za-z0-9.]+', path) or path.lower() in reserved or path.strip('.') == '':
        raise ValueError('Dùng link trang cá nhân, không dùng trang điều hướng Facebook.')
    return f'https://www.facebook.com/{path}/'


def render_content(template, target):
    try:
        fields = list(string.Formatter().parse(template))
        if any(name is not None and (name not in {'ten', 'nganh', 'khu_vuc'} or spec or conversion)
               for _, name, spec, conversion in fields):
            raise ValueError()
        return template.format(ten=target.get('name', ''), nganh=target.get('industry', ''),
                               khu_vuc=target.get('region', '')).strip()
    except (ValueError, KeyError):
        raise ValueError('Nội dung chỉ hỗ trợ biến {ten}, {nganh}, {khu_vuc}.') from None


class OutreachService:
    def __init__(self, bind=None, clock=None):
        self.engine = engine if bind is None else bind
        self.clock = clock or local_now
        metadata.create_all(self.engine)

    def scheduler_enabled(self):
        with self.engine.connect() as db:
            value = db.execute(select(settings.c.enabled).where(settings.c.key == 'scheduler_enabled')).scalar()
            return True if value is None else bool(value)

    def set_scheduler_enabled(self, enabled):
        from sqlalchemy.dialects.sqlite import insert
        with self.engine.begin() as db:
            statement = insert(settings).values(key='scheduler_enabled', enabled=bool(enabled))
            db.execute(statement.on_conflict_do_update(index_elements=['key'], set_={'enabled': bool(enabled)}))

    def save_targets(self, profile, rows):
        if not str(profile).strip():
            raise ValueError('Chọn profile sở hữu danh sách.')
        prepared = [dict(profile=profile, kind=row['kind'], url=normalize_target(row['kind'], row['url']),
                         name=str(row.get('name') or row['url']).strip(), industry=str(row.get('industry') or '').strip(),
                         region=str(row.get('region') or '').strip(), description=str(row.get('description') or ''),
                         joined=bool(row.get('joined')), updated_at=timestamp(self.clock())) for row in rows]
        with self.engine.begin() as db:
            for row in prepared:
                current = db.execute(select(audiences).where(audiences.c.profile == profile,
                    audiences.c.kind == row['kind'], audiences.c.url == row['url'])).mappings().first()
                if current:
                    for key in ('industry', 'region'):
                        row[key] = row[key] or current[key]
                    row['joined'] = row['joined'] or current['joined']
                    db.execute(audiences.update().where(audiences.c.id == current['id']).values(**row))
                else:
                    db.execute(audiences.insert().values(**row))
        return len(prepared)

    def targets(self, profile, kind='', industry='', region='', query=''):
        with self.engine.connect() as db:
            rows = [dict(row) for row in db.execute(select(audiences).where(audiences.c.profile == profile)
                                                   .order_by(audiences.c.id.desc())).mappings()]
        return [row for row in rows if (not kind or row['kind'] == kind)
                and normalize_text(industry) in normalize_text(row['industry'])
                and normalize_text(region) in normalize_text(row['region'])
                and normalize_text(query) in normalize_text(' '.join(str(v) for v in row.values()))]

    def tag_targets(self, profile, ids, industry, region):
        with self.engine.begin() as db:
            db.execute(audiences.update().where(audiences.c.profile == profile, audiences.c.id.in_(ids))
                       .values(industry=industry.strip(), region=region.strip()))

    def remove_targets(self, profile, ids):
        with self.engine.begin() as db:
            db.execute(audiences.delete().where(audiences.c.profile == profile, audiences.c.id.in_(ids)))

    def prepare_schedule(self, *, profile, campaign, action, targets, content='', media=(), run_at=None,
                 repeat_days=0, daily_limit=20, gap_seconds=60):
        if action not in ACTIONS or not profile or not campaign.strip() or not 1 <= len(targets) <= 10:
            raise ValueError('Nhập tên lịch, chọn profile và từ 1 đến 10 đối tượng.')
        if not 1 <= daily_limit <= 500 or not 0 <= gap_seconds <= 86400 or not 0 <= repeat_days <= 365:
            raise ValueError('Giới hạn mỗi ngày, khoảng nghỉ hoặc chu kỳ không hợp lệ.')
        if repeat_days and action not in {'group_post', 'engage'}:
            raise ValueError('Chỉ đăng bài và tương tác có lịch lặp; yêu cầu kết nối và tin nhắn chạy một lần.')
        paths = [str(Path(path).resolve()) for path in media]
        if paths and action != 'group_post':
            raise ValueError('Tệp đính kèm hiện chỉ dùng cho đăng bài nhóm.')
        if any(not Path(path).is_file() for path in paths):
            raise ValueError('Có tệp ảnh/video không còn tồn tại.')
        prepared = []
        for target in targets:
            kind = target.get('kind', '')
            allowed = {'join_group': {'group'}, 'group_post': {'group'}, 'add_friend': {'person'},
                       'engage': {'person', 'post'}, 'message': {'thread'}}[action]
            if kind not in allowed:
                raise ValueError(f'{ACTIONS[action]} không áp dụng cho loại đối tượng đã chọn.')
            url = normalize_target(kind, target['url'])
            text = render_content(content, target)
            if action == 'message' and not text or action == 'group_post' and not (text or paths):
                raise ValueError('Nhập nội dung cần gửi.')
            fingerprint = hashlib.sha256(json.dumps([profile, action, url, text, paths], ensure_ascii=False).encode()).hexdigest()
            prepared.append(dict(campaign=campaign.strip(), profile=profile, action=action, target=url,
                name=target.get('name') or url, content=text, media_json=json.dumps(paths),
                next_at=timestamp(run_at or self.clock()), repeat_days=repeat_days, daily_limit=daily_limit,
                gap_seconds=gap_seconds, status='queued', token='', started_at='', cancel_requested=False,
                last_message='', fingerprint=fingerprint))
        return prepared

    def schedule(self, **options):
        prepared = self.prepare_schedule(**options)
        saved, duplicates = [], 0
        with self.engine.begin() as db:
            for row in prepared:
                existing = db.execute(select(jobs.c.id).where(jobs.c.fingerprint == row['fingerprint'],
                    jobs.c.status.in_(['queued', 'running', 'paused', 'done', 'review']))).first()
                if existing:
                    duplicates += 1
                    continue
                saved.append(db.execute(jobs.insert().values(**row)).inserted_primary_key[0])
        return dict(ids=saved, duplicates=duplicates)

    def running_job(self, job_id, token):
        with self.engine.connect() as db:
            row = db.execute(select(jobs).where(jobs.c.id == job_id, jobs.c.token == token,
                                                jobs.c.status == 'running')).mappings().first()
            return dict(row) if row else None

    def list_jobs(self, profile=''):
        query = select(jobs).order_by(jobs.c.next_at, jobs.c.id)
        if profile:
            query = query.where(jobs.c.profile == profile)
        with self.engine.connect() as db:
            return [dict(row) for row in db.execute(query).mappings()]

    def due_jobs(self):
        with self.engine.connect() as db:
            return [dict(row) for row in db.execute(select(jobs).where(
                jobs.c.status == 'queued', jobs.c.next_at <= timestamp(self.clock()))
                .order_by(jobs.c.next_at, jobs.c.id)).mappings()]

    def control(self, ids, operation):
        with self.engine.begin() as db:
            if operation == 'pause':
                db.execute(jobs.update().where(jobs.c.id.in_(ids), jobs.c.status == 'queued').values(status='paused'))
            elif operation == 'resume':
                db.execute(jobs.update().where(jobs.c.id.in_(ids), jobs.c.status == 'paused').values(status='queued'))
            elif operation == 'cancel':
                db.execute(jobs.update().where(jobs.c.id.in_(ids), jobs.c.status.in_(['queued', 'paused', 'failed', 'review']))
                           .values(status='cancelled'))
                db.execute(jobs.update().where(jobs.c.id.in_(ids), jobs.c.status == 'running').values(cancel_requested=True))
            else:
                raise ValueError('Thao tác lịch không hợp lệ.')

    def recover_stale(self):
        cutoff = timestamp(self.clock() - timedelta(minutes=10))
        with self.engine.begin() as db:
            stale = list(db.execute(select(jobs).where(jobs.c.status == 'running', jobs.c.started_at < cutoff)).mappings())
            for job in stale:
                message = 'Lượt chạy bị gián đoạn. Kiểm tra trên Facebook trước khi tạo lịch mới; không tự gửi lại.'
                db.execute(jobs.update().where(jobs.c.id == job['id']).values(status='review', last_message=message))
                db.execute(activity.update().where(activity.c.token == job['token']).values(
                    status='review', message=message, finished_at=timestamp(self.clock())))
        return len(stale)

    def claim(self, job_id):
        """Reserve one action atomically, including profile cooldown and daily budget."""
        now = self.clock().astimezone(VIETNAM_TZ)
        stamp = timestamp(now)
        day_start = timestamp(now.replace(hour=0, minute=0, second=0, microsecond=0))
        with self.engine.connect() as db:
            db.exec_driver_sql('BEGIN IMMEDIATE')
            try:
                job = db.execute(select(jobs).where(jobs.c.id == job_id, jobs.c.status == 'queued', jobs.c.next_at <= stamp)).mappings().first()
                if not job:
                    db.rollback()
                    return None
                active = db.execute(select(jobs.c.id).where(jobs.c.profile == job['profile'], jobs.c.status == 'running')).first()
                count = db.execute(select(func.count()).select_from(activity).where(activity.c.profile == job['profile'],
                    activity.c.action == job['action'], activity.c.created_at >= day_start)).scalar_one()
                last = db.execute(select(activity.c.created_at).where(activity.c.profile == job['profile'])
                                  .order_by(activity.c.id.desc()).limit(1)).scalar()
                if active or count >= job['daily_limit'] or last and (now - datetime.fromisoformat(last)).total_seconds() < job['gap_seconds']:
                    db.rollback()
                    return None
                token = uuid.uuid4().hex
                db.execute(jobs.update().where(jobs.c.id == job_id).values(status='running', token=token, started_at=stamp))
                db.execute(activity.insert().values(job_id=job_id, token=token, profile=job['profile'], action=job['action'],
                    target=job['target'], name=job['name'], content=job['content'], status='running', message='',
                    created_at=stamp, finished_at=''))
                db.commit()
                return dict(job, token=token, status='running')
            except Exception:
                db.rollback()
                raise

    def is_cancelled(self, job_id, token):
        with self.engine.connect() as db:
            row = db.execute(select(jobs).where(jobs.c.id == job_id, jobs.c.token == token)).mappings().first()
            return not row or row['cancel_requested'] or row['status'] != 'running'

    def finish(self, job_id, token, status, message):
        if status not in RESULT_STATUSES or status == 'running':
            raise ValueError('Kết quả tác vụ không hợp lệ.')
        now = self.clock().astimezone(VIETNAM_TZ)
        with self.engine.begin() as db:
            job = db.execute(select(jobs).where(jobs.c.id == job_id, jobs.c.token == token, jobs.c.status == 'running')).mappings().first()
            if not job:
                return False
            state = {'failed': 'failed', 'review': 'review', 'cancelled': 'cancelled'}.get(status, 'done')
            values = dict(status=state, last_message=str(message))
            if job['repeat_days'] and state == 'done' and not job['cancel_requested']:
                due = datetime.fromisoformat(job['next_at'])
                while due <= now:
                    due += timedelta(days=job['repeat_days'])
                values.update(status='queued', next_at=timestamp(due))
            db.execute(jobs.update().where(jobs.c.id == job_id).values(**values))
            db.execute(activity.update().where(activity.c.token == token).values(
                status=status, message=str(message), finished_at=timestamp(now)))
        return True

    def history(self, day=None, profile='', action='', query=''):
        statement = select(activity).order_by(activity.c.id.desc())
        if day:
            start = datetime.combine(day, datetime.min.time(), tzinfo=VIETNAM_TZ)
            statement = statement.where(activity.c.created_at >= timestamp(start),
                                        activity.c.created_at < timestamp(start + timedelta(days=1)))
        if profile:
            statement = statement.where(activity.c.profile == profile)
        if action:
            statement = statement.where(activity.c.action == action)
        with self.engine.connect() as db:
            rows = [dict(row) for row in db.execute(statement).mappings()]
        return [row for row in rows if normalize_text(query) in normalize_text(' '.join(str(v) for v in row.values()))]
