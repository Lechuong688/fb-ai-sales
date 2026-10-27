from sqlalchemy import select

from backend.database.db import Base, SessionLocal, engine
from backend.database.models.profile_group import ProfileGroup


class ProfileGroupRepository:
    def __init__(self):
        Base.metadata.create_all(bind=engine, tables=[ProfileGroup.__table__])

    def link(self, profile, group_id):
        with SessionLocal() as db:
            existing = db.execute(
                select(ProfileGroup).where(
                    ProfileGroup.profile == profile,
                    ProfileGroup.group_id == group_id,
                )
            ).scalar_one_or_none()
            if existing:
                return existing
            link = ProfileGroup(profile=profile, group_id=group_id)
            db.add(link)
            db.commit()
            db.refresh(link)
            return link

    def get_groups_for_profile(self, profile):
        from backend.database.models.group import Group

        with SessionLocal() as db:
            return (
                db.query(Group)
                .join(ProfileGroup, ProfileGroup.group_id == Group.id)
                .filter(ProfileGroup.profile == profile)
                .order_by(Group.name)
                .all()
            )

    def sync_profile_groups(self, profile, group_ids):
        group_ids = {int(group_id) for group_id in group_ids if group_id}
        with SessionLocal() as db:
            existing = {
                link.group_id: link
                for link in db.query(ProfileGroup)
                .filter(ProfileGroup.profile == profile)
                .all()
            }
            for group_id, link in existing.items():
                if group_id not in group_ids:
                    db.delete(link)
            for group_id in group_ids - set(existing):
                db.add(ProfileGroup(profile=profile, group_id=group_id))
            db.commit()

    def unlink_many(self, profile, group_ids):
        group_ids = {int(group_id) for group_id in group_ids if group_id}
        if not group_ids:
            return
        with SessionLocal() as db:
            db.query(ProfileGroup).filter(
                ProfileGroup.profile == profile,
                ProfileGroup.group_id.in_(group_ids),
            ).delete(synchronize_session=False)
            db.commit()
