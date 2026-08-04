from sqlalchemy import Column, Integer, String

from backend.database.db import Base


class Group(Base):

    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, autoincrement=True)

    name = Column(String(255), nullable=False)

    url = Column(String(500), unique=True, nullable=False)

    privacy = Column(String(50), default="Unknown")

    members = Column(Integer, default=0)

    status = Column(String(30), default="New")