from backend.database.models.group import Group
from backend.database.repository.group_repository import GroupRepository


class GroupService:

    def __init__(self):
        self.repo = GroupRepository()

    def get_all(self):
        return self.repo.get_all()

    def add_group(self, url):

        # Không thêm trùng
        if self.repo.get_by_url(url):
            return None

        group = Group(
            name="Đang lấy...",
            url=url,
            privacy="Unknown",
            members=0,
            status="Pending"
        )

        return self.repo.add(group)

    def delete_group(self, group_id):
        self.repo.delete(group_id)