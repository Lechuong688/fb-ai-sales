from PySide6.QtWidgets import (
    QTableWidget,
    QTableWidgetItem,
)

from frontend.pages.base_page import BasePage
from frontend.widgets.base_table import BaseTable

class AccountsPage(BasePage):

    def __init__(self):
        super().__init__(
            "Accounts",
            "Quản lý tài khoản Facebook",
            "➕ Thêm tài khoản"
        )

        table = BaseTable()

        table.setColumnCount(5)

        table.setHorizontalHeaderLabels([
            "Tên",
            "UID",
            "Trạng thái",
            "Profile",
            "Hành động"
        ])

        table.setRowCount(2)

        table.setItem(0, 0, QTableWidgetItem("Kitchen Care"))
        table.setItem(0, 1, QTableWidgetItem("10000123"))
        table.setItem(0, 2, QTableWidgetItem("🟢 Online"))
        table.setItem(0, 3, QTableWidgetItem("Profile 1"))
        table.setItem(0, 4, QTableWidgetItem("Login"))

        table.setItem(1, 0, QTableWidgetItem("Bosch"))
        table.setItem(1, 1, QTableWidgetItem("10000888"))
        table.setItem(1, 2, QTableWidgetItem("🔴 Offline"))
        table.setItem(1, 3, QTableWidgetItem("Profile 2"))
        table.setItem(1, 4, QTableWidgetItem("Login"))

        self.set_content(table)