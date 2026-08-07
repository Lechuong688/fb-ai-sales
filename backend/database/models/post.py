from datetime import datetime

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import relationship

from backend.database.db import Base


class Post(Base):

    __tablename__ = "posts"

    id = Column(Integer, primary_key=True)

    group_id = Column(
        Integer,
        ForeignKey("groups.id")
    )

    post_id = Column(
        String,
        unique=True
    )

    author = Column(String)

    content = Column(String)

    created_at = Column(
        DateTime,
        default=datetime.now
    )

    group = relationship("Group")