from backend.database.db import SessionLocal
from backend.database.models.group import Group


class GroupRepository:

    def get_all(self):
        db = SessionLocal()

        try:
            return db.query(Group).all()
        finally:
            db.close()

    def add(self, group):
        db = SessionLocal()

        try:
            db.add(group)
            db.commit()
            db.refresh(group)
            return group
        finally:
            db.close()

    def delete(self, group_id):
        db = SessionLocal()

        try:
            group = db.query(Group).filter(
                Group.id == group_id
            ).first()

            if group:
                db.delete(group)
                db.commit()
        finally:
            db.close()

    def get_by_url(self, url):
        db = SessionLocal()

        try:
            return db.query(Group).filter(
                Group.url == url
            ).first()
        finally:
            db.close()