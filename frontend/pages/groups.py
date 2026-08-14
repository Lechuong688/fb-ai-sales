from PySide6.QtWidgets import QTableWidgetItem
from PySide6.QtWidgets import QPushButton
from functools import partial

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

        self.table.setColumnCount(5)

        self.table.setHorizontalHeaderLabels([
            "Tên nhóm",
            "URL",
            "Members",
            "Privacy",
            "Status"
        ])

        self.group_service = GroupService()

        self.load_groups()

        self.set_content(
            self.table
        )

    def load_groups(self):

        groups = self.group_service.get_all()

        self.table.setRowCount(
            len(groups)
        )

        for row, group in enumerate(groups):

            self.table.setItem(
                row,
                0,
                QTableWidgetItem(
                    group.name or ""
                )
            )

            self.table.setItem(
                row,
                1,
                QTableWidgetItem(
                    group.url or ""
                )
            )

            self.table.setItem(
                row,
                2,
                QTableWidgetItem(
                    str(
                        group.member_count
                        or "0"
                    )
                )
            )

            self.table.setItem(
                row,
                3,
                QTableWidgetItem(
                    group.privacy or "Unknown"
                )
            )

            self.table.setItem(
                row,
                4,
                QTableWidgetItem(
                    group.status or "Ready"
                )
            )

    def add_group(self):

        from PySide6.QtWidgets import (
            QInputDialog
        )

        url, ok = QInputDialog.getText(
            self,
            "Thêm Facebook Group",
            "URL Group:"
        )

        if not ok:
            return

        url = url.strip()

        if not url:
            return

        self.group_service.create(
            "Facebook Group",
            url
        )

        self.load_groups()