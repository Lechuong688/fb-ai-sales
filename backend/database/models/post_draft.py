from datetime import datetime

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.db import Base


class PostDraft(Base):
    __tablename__ = "post_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    media_paths: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    target_profiles: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    target_groups: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )
