from backend.database.db import Base
from backend.database.db import engine

import backend.models.account
import backend.models.group


def init_database():

    Base.metadata.create_all(engine)


if __name__ == "__main__":

    init_database()

    print("Database created.")