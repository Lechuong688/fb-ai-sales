from backend.database.models.group import Group
from backend.database.repositories.group_repository import GroupRepository


class GroupService:

    def __init__(self):
        self.repo = GroupRepository()

    def get_all(self):
        return self.repo.get_all()

    def create(self, name, url):

        if self.repo.get_by_url(url):
            return

        group = Group(
            name=name,
            url=url,
            member_count="0",
            privacy="Unknown",
            status="Joined"
        )

        self.repo.add(group)

    def delete(self, group_id):
        self.repo.delete(group_id)

    def create_demo(self):

        if self.get_all():
            return

        self.create(
            "Kitchen Care",
            "https://facebook.com/groups/1"
        )

        self.create(
            "Bosch Việt Nam",
            "https://facebook.com/groups/2"
        )