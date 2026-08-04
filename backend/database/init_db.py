from backend.database.db import Base, engine

# Import tất cả model để SQLAlchemy đăng ký bảng
from backend.database.models.account import Account
from backend.database.models.group import Group


def init_database():
    Base.metadata.create_all(bind=engine)
    print("===================================")
    print(" Database initialized successfully ")
    print("===================================")


if __name__ == "__main__":
    init_database()