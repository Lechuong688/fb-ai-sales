import json

from backend.database.db import Base, SessionLocal, engine
from backend.database.models.post_draft import PostDraft


class PostDraftRepository:
    def __init__(self):
        Base.metadata.create_all(bind=engine, tables=[PostDraft.__table__])

    def get_all(self):
        with SessionLocal() as db:
            return db.query(PostDraft).order_by(PostDraft.updated_at.desc()).all()

    def get(self, draft_id):
        with SessionLocal() as db:
            return db.query(PostDraft).filter(PostDraft.id == draft_id).first()

    def save(self, draft_id, content, media_paths, target_profiles, target_groups):
        with SessionLocal() as db:
            draft = (
                db.query(PostDraft).filter(PostDraft.id == draft_id).first()
                if draft_id
                else None
            )
            if draft is None:
                draft = PostDraft()
                db.add(draft)
            draft.content = content
            draft.media_paths = json.dumps(media_paths, ensure_ascii=False)
            draft.target_profiles = json.dumps(target_profiles, ensure_ascii=False)
            draft.target_groups = json.dumps(target_groups, ensure_ascii=False)
            db.commit()
            db.refresh(draft)
            return draft

    def delete(self, draft_id):
        with SessionLocal() as db:
            draft = db.query(PostDraft).filter(PostDraft.id == draft_id).first()
            if draft:
                db.delete(draft)
                db.commit()
