from functools import partial

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QPushButton
from PySide6.QtWidgets import QTableWidgetItem

from backend.services.account_service import AccountService
from backend.services.browser_service import BrowserService
from backend.signals import signals
from backend.workers.browser_worker import BrowserWorker

from frontend.dialogs.account_dialog import AccountDialog
from frontend.pages.base_page import BasePage
from frontend.widgets.base_table import BaseTable


class AccountsPage(BasePage):

    def __init__(self):

        super().__init__(
            title="Accounts",
            description="Quản lý tài khoản Facebook",
            buttons=[
                ("➕ Thêm", self.add_account),
                ("🔄 Refresh", self.load_accounts)
            ]
        )
        self._threads = []
        self.table = BaseTable()

        self.table.setColumnCount(5)

        self.table.setHorizontalHeaderLabels([
            "Tên",
            "UID",
            "Trạng thái",
            "Profile",
            "Hành động"
        ])

        self.account_service = AccountService()

        self.load_accounts()

        self.set_content(self.table)

        signals.facebook_login.connect(
            self.on_login
        )

        if hasattr(signals, "account_updated"):
            signals.account_updated.connect(
                self.load_accounts
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

                button = QPushButton("🟢 Online")
                button.setEnabled(False)

            else:

                button = QPushButton("🟢 Open")

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

        profile = account.profile.strip()

        # Account cũ chưa có Profile
        if not profile:

            profile = self.account_service._generate_profile(
                account.name
            )

            account.profile = profile

            self.account_service.update(
                account
            )

            self.load_accounts()

            print(
                f"Đã tự tạo Profile: {profile}"
            )

        thread = QThread()

        worker = BrowserWorker()

        self._threads.append(thread)

        worker.moveToThread(thread)

        thread.started.connect(
            lambda: worker.open_profile(account)
        )

        worker.account_updated.connect(
            self.on_account_updated
        )

        worker.groups_synced.connect(
            self.on_groups_synced
        )

        worker.error.connect(
            self.on_browser_error
        )

        worker.finished.connect(
            thread.quit
        )

        worker.finished.connect(
            worker.deleteLater
        )

        thread.finished.connect(
            thread.deleteLater
        )

        thread.finished.connect(
            lambda: self._remove_thread(thread)
        )

        thread.start()
    
    def start_sync(self, profile):

        self.sync_thread = QThread()

        self.sync_worker = SyncWorker()

        self.sync_worker.moveToThread(
            self.sync_thread
        )

        self.sync_thread.started.connect(
            lambda: self.sync_worker.sync(profile)
        )

        self.sync_worker.finished.connect(
            self.sync_thread.quit
        )

        self.sync_worker.finished.connect(
            self.sync_worker.deleteLater
        )

        self.sync_thread.finished.connect(
            self.sync_thread.deleteLater
        )

        self.sync_thread.finished.connect(
            self.load_accounts
        )

        self.sync_worker.error.connect(
            print
        )

        self.sync_thread.start()

    def on_login(self, account):

        self.load_accounts()

    def add_account(self):

        dialog = AccountDialog()

        if dialog.exec():

            data = dialog.get_data()

            self.account_service.create(
                data["name"],
                data["uid"],
                data["profile"]
            )

            self.load_accounts()

    def on_account_updated(self, account):

        self.load_accounts()


    def on_groups_synced(self, count):

        print(
            f"Đã đồng bộ {count} nhóm mới."
        )


    def on_browser_error(self, error):

        print(
            f"Browser error: {error}"
        )


    def _remove_thread(self, thread):

        if thread in self._threads:

            self._threads.remove(
                thread
            )