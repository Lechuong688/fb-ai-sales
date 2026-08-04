from backend.database.db import SessionLocal
from backend.database.models.account import Account


class AccountRepository:

    def get_all(self):

        db = SessionLocal()

        try:
            return db.query(Account).all()

        finally:
            db.close()

    def add(self, account):

        db = SessionLocal()

        try:
            db.add(account)

            db.commit()

            db.refresh(account)

            return account

        finally:
            db.close()

    def delete(self, account_id):

        db = SessionLocal()

        try:

            account = db.query(Account).filter(
                Account.id == account_id
            ).first()

            if account:

                db.delete(account)

                db.commit()

        finally:

            db.close()

    def get_by_uid(self, uid):

        db = SessionLocal()

        try:

            return db.query(Account).filter(
                Account.uid == uid
            ).first()

        finally:

            db.close()

    def update(self, account):

        db = SessionLocal()

        try:

            db.merge(account)

            db.commit()

        finally:

            db.close()

    def get(self, account_id):

        db = SessionLocal()

        try:

            return db.query(Account).filter(
                Account.id == account_id
            ).first()

        finally:

            db.close()