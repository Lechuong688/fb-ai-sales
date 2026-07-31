from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTableWidget,
    QTableWidgetItem,
)

from frontend.widgets.page_header import PageHeader


class AccountsPage(QWidget):
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)

        layout.addWidget(
            PageHeader(
                "Accounts",
                "Quản lý tài khoản Facebook"
            )
        )

        table = QTableWidget()
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
        table.setItem(0, 2, QTableWidgetItem("Online"))
        table.setItem(0, 3, QTableWidgetItem("Profile 1"))
        table.setItem(0, 4, QTableWidgetItem("Login"))

        table.setItem(1, 0, QTableWidgetItem("Bosch"))
        table.setItem(1, 1, QTableWidgetItem("10000888"))
        table.setItem(1, 2, QTableWidgetItem("Offline"))
        table.setItem(1, 3, QTableWidgetItem("Profile 2"))
        table.setItem(1, 4, QTableWidgetItem("Login"))

        layout.addWidget(table)