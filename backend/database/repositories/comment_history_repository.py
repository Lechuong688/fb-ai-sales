from datetime import datetime

from sqlalchemy import desc

from backend.database.db import Base, SessionLocal, engine
from backend.database.models.comment_history import CommentHistory


class CommentHistoryRepository:
    def __init__(self, db_engine=None, session_factory=None):
        self.engine = db_engine or engine
        self.session_factory = session_factory or SessionLocal
        Base.metadata.create_all(
            bind=self.engine,
            tables=[CommentHistory.__table__],
        )

    def was_sent(self, account_profile, post_url):
        db = self.session_factory()
        try:
            return (
                db.query(CommentHistory.id)
                .filter(
                    CommentHistory.account_profile == account_profile,
                    CommentHistory.post_url == post_url,
                    CommentHistory.status == "sent",
                )
                .first()
                is not None
            )
        finally:
            db.close()

    def record(self, account_profile, post_url, comment_text, status, error=""):
        db = self.session_factory()
        try:
            record = (
                db.query(CommentHistory)
                .filter(
                    CommentHistory.account_profile == account_profile,
                    CommentHistory.post_url == post_url,
                )
                .first()
            )
            if record is None:
                record = CommentHistory(
                    account_profile=account_profile,
                    post_url=post_url,
                    comment_text=comment_text,
                    status=status,
                    error=error,
                )
                db.add(record)
            else:
                record.comment_text = comment_text
                record.status = status
                record.error = error
                record.created_at = datetime.now()

            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_recent(self, limit=12):
        db = self.session_factory()
        try:
            records = (
                db.query(CommentHistory)
                .order_by(desc(CommentHistory.created_at))
                .limit(limit)
                .all()
            )
            return [
                {
                    "account_profile": record.account_profile,
                    "post_url": record.post_url,
                    "comment_text": record.comment_text,
                    "status": record.status,
                    "error": record.error,
                    "created_at": record.created_at,
                }
                for record in records
            ]
        finally:
            db.close()
