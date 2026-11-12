from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.db import Base


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Lead(Base):
    """A buyer-intent post, not a verified contact or a sent comment."""

    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_url: Mapped[str] = mapped_column(String, unique=True, index=True)
    author: Mapped[str] = mapped_column(Text, default="")
    post_text: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    source_name: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[str] = mapped_column(String, default="")
    published_until: Mapped[str] = mapped_column(String, default="")
    product_label: Mapped[str] = mapped_column(Text, default="")
    skus_json: Mapped[str] = mapped_column(Text, default="[]")
    rule_name: Mapped[str] = mapped_column(Text, default="")
    rule_reason: Mapped[str] = mapped_column(Text, default="")
    requires_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    suggested_comment: Mapped[str] = mapped_column(Text, default="")
    draft_comment: Mapped[str] = mapped_column(Text, default="")
    draft_origin: Mapped[str] = mapped_column(String, default="generated")
    review_status: Mapped[str] = mapped_column(String, default="pending", index=True)
    workflow_status: Mapped[str] = mapped_column(String, default="new", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    profiles_json: Mapped[str] = mapped_column(Text, default="[]")
    search_text: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
