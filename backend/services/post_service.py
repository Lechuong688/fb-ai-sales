from backend.database.models.post import Post
from backend.database.repositories.post_repository import (
    PostRepository
)


class PostService:

    def __init__(self):

        self.repo = PostRepository()

    def create(
        self,
        group_id,
        post_id,
        author,
        content
    ):

        if self.repo.get_by_post_id(
            post_id
        ):
            return

        post = Post(
            group_id=group_id,
            post_id=post_id,
            author=author,
            content=content
        )

        self.repo.add(post)

    def get_all(self):

        return self.repo.get_all()