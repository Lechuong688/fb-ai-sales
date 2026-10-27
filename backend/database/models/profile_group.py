from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.db import Base


class ProfileGroup(Base):
    """Links a saved Facebook group to the profile that discovered it."""

    __tablename__ = "profile_groups"
    __table_args__ = (UniqueConstraint("profile", "group_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
