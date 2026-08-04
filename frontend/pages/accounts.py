from PySide6.QtWidgets import QTableWidgetItem

from backend.services.account_service import AccountService
from frontend.pages.base_page import BasePage
from frontend.widgets.base_table import BaseTable
from PySide6.QtWidgets import QPushButton
from functools import partial
from backend.services.browser_service import BrowserService
from backend.signals import signals

class AccountsPage(BasePage):

    def __init__(self):
        super().__init__(
            title="Accounts",
            description="Quản lý tài khoản Facebook",
            buttons=[
                ("➕ Thêm", self.add_account),
                ("🔄 Refresh", self.load_accounts),
            ]
        )

        # Tạo bảng
        self.table = BaseTable()

        self.table.setColumnCount(5)

        self.table.setHorizontalHeaderLabels([
            "Tên",
            "UID",
            "Trạng thái",
            "Profile",
            "Hành động"
        ])

        # Service
        self.account_service = AccountService()

        # Dữ liệu mẫu
        self.account_service.load_demo()

        # Hiển thị dữ liệu
        self.load_accounts()

        # Đưa bảng vào BasePage
        self.set_content(self.table)

        signals.facebook_login.connect(
            self.on_login
        )

    def load_accounts(self):

        accounts = self.account_service.get_all()

        self.table.setRowCount(len(accounts))

        for row, account in enumerate(accounts):

            self.table.setItem(
                row,
                0,
                QTableWidgetItem(account.name)
            )

            self.table.setItem(
                row,
                1,
                QTableWidgetItem(account.uid)
            )

            self.table.setItem(
                row,
                2,
                QTableWidgetItem(account.status)
            )

            self.table.setItem(
                row,
                3,
                QTableWidgetItem(account.profile)
            )

            if account.status == "Online":
                button = QPushButton("🟢 Connected")
                button.setEnabled(False)
            else:
                button = QPushButton("🔑 Login")

                button.clicked.connect(
                    partial(
                        self.login_account,
                        account
                    )
                )

            self.table.setCellWidget(
                row,
                4,
                button
            )
    def login_account(self, account):

        BrowserService.login(account)

        self.load_accounts()
    def on_login(self, account):

        self.load_accounts()

    def add_account(self):
        print("Add Account")