from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.db import Base


class CommentHistory(Base):
    __tablename__ = "comment_history"
    __table_args__ = (
        UniqueConstraint(
            "account_profile",
            "post_url",
            name="uq_comment_history_profile_post",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_profile: Mapped[str] = mapped_column(String(100), nullable=False)
    post_url: Mapped[str] = mapped_column(Text, nullable=False)
    comment_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
