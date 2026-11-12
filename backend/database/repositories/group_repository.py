from backend.database.db import SessionLocal
from backend.database.models.group import Group
from backend.database.models.profile_group import ProfileGroup


class GroupRepository:

    def __init__(self, session_factory=None):
        self.session_factory = session_factory or SessionLocal

    def sync_discovered_groups(self, profile, groups, replace=False):
        """Commit group records and membership together; roll back on any failure."""
        added = 0
        with self.session_factory() as db, db.begin():
            links = {
                link.group_id: link
                for link in db.query(ProfileGroup).filter_by(profile=profile).all()
            }
            seen_ids = set()
            for item in groups:
                group = db.query(Group).filter_by(url=item["url"]).first()
                if group is None:
                    group = Group(
                        name=item["name"], url=item["url"],
                        member_count="0", privacy="Unknown", status="Ready",
                    )
                    db.add(group)
                    db.flush()
                    added += 1
                elif not item["name"].startswith("Facebook Group"):
                    group.name = item["name"]
                seen_ids.add(group.id)
                if group.id not in links:
                    link = ProfileGroup(profile=profile, group_id=group.id)
                    db.add(link)
                    links[group.id] = link
            if replace:
                for group_id, link in links.items():
                    if group_id not in seen_ids:
                        db.delete(link)
        return added

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

    def update(self, group):
        db = SessionLocal()
        try:
            db.merge(group)
            db.commit()
        finally:
            db.close()
