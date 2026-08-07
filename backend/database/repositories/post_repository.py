from backend.database.db import SessionLocal
from backend.database.models.post import Post


class PostRepository:

    def get_all(self):

        db = SessionLocal()

        try:
            return db.query(Post).all()

        finally:
            db.close()

    def add(self, post):

        db = SessionLocal()

        try:

            db.add(post)

            db.commit()

            db.refresh(post)

            return post

        finally:

            db.close()

    def get_by_post_id(self, post_id):

        db = SessionLocal()

        try:

            return db.query(Post).filter(
                Post.post_id == post_id
            ).first()

        finally:

            db.close()