from PySide6.QtWidgets import QTableWidgetItem

from backend.services.group_service import GroupService
from frontend.pages.base_page import BasePage
from frontend.widgets.base_table import BaseTable


class GroupsPage(BasePage):

    def __init__(self):
        super().__init__(
            title="Groups",
            description="Quản lý nhóm Facebook",
            buttons=[
                ("➕ Thêm nhóm", self.add_group),
                ("🔄 Refresh", self.load_groups),
            ]
        )

        self.table = BaseTable()

        self.table.setColumnCount(4)

        self.table.setHorizontalHeaderLabels([
            "Tên",
            "URL",
            "Members",
            "Status"
        ])

        self.group_service = GroupService()

        self.group_service.create_demo()

        self.load_groups()

        self.set_content(self.table)

    def load_groups(self):

        groups = self.group_service.get_all()

        self.table.setRowCount(0)
        self.table.setRowCount(len(groups))

        for row, group in enumerate(groups):

            self.table.setItem(
                row,
                0,
                QTableWidgetItem(group.name)
            )

            self.table.setItem(
                row,
                1,
                QTableWidgetItem(group.url)
            )

            self.table.setItem(
                row,
                2,
                QTableWidgetItem(str(group.member_count))
            )

            self.table.setItem(
                row,
                3,
                QTableWidgetItem(group.status)
            )

    def add_group(self):
        print("Add Group")