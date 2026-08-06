from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from backend.database.db import Base


class Account(Base):

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    name: Mapped[str] = mapped_column(
        String(100)
    )

    uid: Mapped[str] = mapped_column(
        String(50)
    )

    profile: Mapped[str] = mapped_column(
        String(100),
        unique=True
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="Offline"
    )

    cookie: Mapped[str] = mapped_column(
        String,
        default=""
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now
    )