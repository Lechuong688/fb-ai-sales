from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from backend.database.db import Base


class Group(Base):

    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    name: Mapped[str] = mapped_column(
        String(200)
    )

    url: Mapped[str] = mapped_column(
        String,
        unique=True
    )

    member_count: Mapped[str] = mapped_column(
        String(30),
        default="0"
    )

    privacy: Mapped[str] = mapped_column(
        String(30),
        default="Public"
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="Waiting"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now
    )