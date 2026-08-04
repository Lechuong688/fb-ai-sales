from PySide6.QtWidgets import (
    QPushButton,
    QTableWidgetItem,
)

from frontend.pages.base_page import BasePage
from frontend.widgets.base_table import BaseTable


class GroupsPage(BasePage):

    def __init__(self):
        super().__init__(
            title="Groups",
            description="Quản lý các nhóm Facebook",
            buttons=[
                ("➕ Thêm nhóm", self.add_group),
                ("🔄 Refresh", self.load_groups),
            ]
        )

        self.table = BaseTable()

        self.table.setColumnCount(6)

        self.table.setHorizontalHeaderLabels([
            "Tên nhóm",
            "Thành viên",
            "Quyền riêng tư",
            "Trạng thái",
            "Mở",
            "Xóa"
        ])

        self.set_content(self.table)

        self.load_groups()

    def load_groups(self):

        demo = [
            ("Kitchen Care", "120000", "Public", "Ready"),
            ("Bosch Việt Nam", "56000", "Private", "Ready"),
            ("Máy rửa bát", "43000", "Public", "Ready"),
        ]

        self.table.setRowCount(len(demo))

        for row, group in enumerate(demo):

            self.table.setItem(
                row, 0,
                QTableWidgetItem(group[0])
            )

            self.table.setItem(
                row, 1,
                QTableWidgetItem(group[1])
            )

            self.table.setItem(
                row, 2,
                QTableWidgetItem(group[2])
            )

            self.table.setItem(
                row, 3,
                QTableWidgetItem(group[3])
            )

            open_btn = QPushButton("🌐 Open")
            delete_btn = QPushButton("🗑 Delete")

            self.table.setCellWidget(row, 4, open_btn)
            self.table.setCellWidget(row, 5, delete_btn)

    def add_group(self):
        print("Add Group")