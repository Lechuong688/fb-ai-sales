from sqlalchemy import Column, Integer, String

from backend.database.db import Base


class Account(Base):

    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)

    name = Column(String(255), nullable=False)

    uid = Column(String(100), nullable=False)

    profile = Column(String(255), nullable=False)

    status = Column(String(30), default="Offline")