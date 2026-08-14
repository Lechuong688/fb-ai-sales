from urllib.parse import urlparse

from backend.database.models.group import Group
from backend.database.repositories.group_repository import GroupRepository


class GroupService:

    def __init__(self):

        self.repo = GroupRepository()

    def get_all(self):

        return self.repo.get_all()

    def create(self, name, url):

        name = (name or "").strip()
        url = (url or "").strip()

        if not url:
            return None

        # Không thêm trùng
        existing = self.repo.get_by_url(url)

        if existing:
            return existing

        group = Group(
            name=name or "Facebook Group",
            url=url,
            member_count="0",
            privacy="Unknown",
            status="Ready"
        )

        return self.repo.add(
            group
        )

    def delete(self, group_id):

        self.repo.delete(
            group_id
        )