from functools import partial

from PySide6.QtCore import QThread, QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QAbstractItemView, QMessageBox, QPushButton
from PySide6.QtWidgets import QTableWidgetItem

from backend.services.account_service import AccountService
from backend.services.profile_label_service import ProfileLabelService
from backend.browser.pool import browser_pool
from backend.browser.window_layout import tile_windows
from backend.signals import signals
from backend.workers.browser_worker import BrowserWorker

from frontend.pages.base_page import BasePage
from frontend.widgets.base_table import BaseTable


class AccountsPage(BasePage):

    def __init__(self):

        super().__init__(
            title="Accounts",
            description="Quản lý tài khoản Facebook",
            buttons=[
                ("➕ Add Facebook", self.add_facebook),
                ("▶ Open All", self.open_all_accounts),
                ("■ Stop All", self.stop_all_accounts),
                ("🔄 Refresh", self.load_accounts),
            ]
        )
        self._sessions = {}
        self._batch_window_bounds = None
        self.profile_label_service = ProfileLabelService()
        self.table = BaseTable()
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked)
        self.table.setFocusPolicy(Qt.StrongFocus)
        self.table.itemChanged.connect(self.on_table_item_changed)

        self.table.setColumnCount(5)

        self.table.setHorizontalHeaderLabels([
            "Tên",
            "UID",
            "Trạng thái",
            "Profile / ghi chú",
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

        self.table.blockSignals(True)
        self.table.setRowCount(len(accounts))

        for row, account in enumerate(accounts):

            session = browser_pool.get_session(account.profile)
            is_online = bool(
                session
                and session.running
                and session.logged_in
            )
            worker_entry = self._sessions.get(account.profile)
            is_starting = bool(worker_entry and worker_entry["starting"])
            is_stopping = bool(worker_entry and worker_entry["stopping"])

            name_item = QTableWidgetItem(account.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, name_item)

            uid_item = QTableWidgetItem(
                account.uid if (account.uid or "").isdigit() else ""
            )
            uid_item.setFlags(uid_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, uid_item)

            status_item = QTableWidgetItem(
                "Stopping" if is_stopping else
                "Online" if is_online else
                "Starting" if is_starting else
                "Offline"
            )
            status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 2, status_item)

            profile_item = QTableWidgetItem(
                self.profile_label_service.get_label(account.profile)
            )
            profile_item.setData(Qt.UserRole, account.profile)
            profile_item.setToolTip(
                f"Double-click to edit this label. Browser data stays in "
                f"data/profiles/{account.profile}."
            )
            self.table.setItem(row, 3, profile_item)

            if worker_entry and worker_entry["stopping"]:
                button = QPushButton("Stopping…")
                button.setObjectName("accountPendingButton")
                button.setEnabled(False)
            elif worker_entry and (is_online or worker_entry["ready"]):
                button = QPushButton("■ Stop")
                button.setObjectName("accountStopButton")
                button.clicked.connect(
                    partial(self.stop_account, account.profile)
                )
            elif is_starting:
                button = QPushButton("Starting…")
                button.setObjectName("accountPendingButton")
                button.setEnabled(False)
            else:
                button = QPushButton("▶ Open")
                button.setObjectName("accountOpenButton")
                button.clicked.connect(
                    partial(self.login_account, account)
                )

            self.table.setCellWidget(
                row,
                4,
                button
            )

        self.table.blockSignals(False)

    def on_table_item_changed(self, item):
        if item.column() != 3:
            return

        profile = item.data(Qt.UserRole)
        if not profile:
            return

        try:
            label = self.profile_label_service.set_label(
                profile,
                item.text(),
            )
            self.table.blockSignals(True)
            item.setText(label)
            item.setToolTip(
                f"Double-click to edit this label. Browser data stays in "
                f"data/profiles/{profile}."
            )
            self.table.blockSignals(False)
        except Exception as exc:
            self.table.blockSignals(True)
            item.setText(self.profile_label_service.get_label(profile))
            self.table.blockSignals(False)
            QMessageBox.warning(self, "Profile label", str(exc))

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

            QTimer.singleShot(0, self.load_accounts)

            print(
                f"Đã tự tạo Profile: {profile}"
            )

        bounds_by_profile = self._window_bounds_for(profile)
        for active_profile, bounds in bounds_by_profile.items():
            entry = self._sessions.get(active_profile)
            if (
                entry
                and (entry["starting"] or entry["ready"])
                and not entry["stopping"]
            ):
                entry["worker"].tile_requested.emit(bounds)

        entry = self._sessions.get(profile)
        if entry:
            if entry["starting"] or entry["ready"] or entry["stopping"]:
                return
            entry["account"] = account
            entry["starting"] = True
            entry["worker"].cancel_event.clear()
            entry["worker"].start_requested.emit(
                {"account": account, "window_bounds": bounds_by_profile.get(profile)}
            )
            QTimer.singleShot(0, self.load_accounts)
            return

        thread = QThread(self)
        worker = BrowserWorker()
        worker.moveToThread(thread)
        browser_pool.register_worker(profile, worker)
        self._sessions[profile] = {
            "thread": thread,
            "worker": worker,
            "ready": False,
            "starting": True,
            "stopping": False,
            "account": account,
        }

        worker.account_updated.connect(
            self.on_account_updated
        )

        worker.groups_synced.connect(
            self.on_groups_synced
        )

        worker.error.connect(
            self.on_browser_error
        )
        worker.ready.connect(
            self.on_session_ready
        )
        worker.session_stopped.connect(
            self.on_session_stopped
        )
        thread.finished.connect(
            worker.deleteLater
        )
        thread.finished.connect(
            thread.deleteLater
        )
        thread.finished.connect(
            partial(self._remove_session, profile)
        )

        thread.start()
        worker.start_requested.emit(
            {"account": account, "window_bounds": bounds_by_profile.get(profile)}
        )
        QTimer.singleShot(0, self.load_accounts)

    def _window_bounds_for(self, target_profile):
        if self._batch_window_bounds is not None:
            return self._batch_window_bounds

        profiles = []
        for account in self.account_service.get_all():
            profile = (account.profile or "").strip()
            entry = self._sessions.get(profile)
            active = bool(
                entry
                and (entry["starting"] or entry["ready"])
                and not entry["stopping"]
            )
            if profile and (active or profile == target_profile):
                profiles.append(profile)
        if target_profile not in profiles:
            profiles.append(target_profile)

        return self._tile_bounds(profiles)

    @staticmethod
    def _tile_bounds(profiles):
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return {}
        area = screen.availableGeometry()
        return tile_windows(
            profiles,
            area.x(),
            area.y(),
            area.width(),
            area.height(),
        )

    def open_all_accounts(self):
        accounts = self.account_service.get_all()
        for account in accounts:
            if not (account.profile or "").strip():
                account.profile = self.account_service._generate_profile(account.name)
                self.account_service.update(account)
        profiles = [(account.profile or "").strip() for account in accounts]
        profiles = [profile for profile in profiles if profile]
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self._batch_window_bounds = tile_windows(
                profiles, area.x(), area.y(), area.width(), area.height()
            )
        for profile, bounds in (self._batch_window_bounds or {}).items():
            entry = self._sessions.get(profile)
            if entry and (entry["starting"] or entry["ready"]) and not entry["stopping"]:
                entry["worker"].tile_requested.emit(bounds)
        try:
            for account in accounts:
                entry = self._sessions.get(account.profile)
                if not entry or not (
                    entry["starting"] or entry["ready"] or entry["stopping"]
                ):
                    self.login_account(account)
        finally:
            self._batch_window_bounds = None

    def stop_account(self, profile):
        entry = self._sessions.get(profile)
        if not entry or entry["stopping"]:
            return

        entry["stopping"] = True
        remaining = [
            account.profile
            for account in self.account_service.get_all()
            if account.profile != profile
            and (
                (self._sessions.get(account.profile) or {}).get("ready")
                or (self._sessions.get(account.profile) or {}).get("starting")
            )
            and not (self._sessions.get(account.profile) or {}).get("stopping")
        ]
        for remaining_profile, bounds in self._tile_bounds(remaining).items():
            remaining_entry = self._sessions.get(remaining_profile)
            if remaining_entry:
                remaining_entry["worker"].tile_requested.emit(bounds)
        worker = entry["worker"]
        worker.cancel_event.set()
        worker.stop_requested.emit()
        QTimer.singleShot(0, self.load_accounts)

    def stop_all_accounts(self):
        for profile in list(self._sessions):
            self.stop_account(profile)

    def on_session_ready(self, profile):
        entry = self._sessions.get(profile)
        if entry:
            entry["ready"] = True
            entry["starting"] = False
        self.load_accounts()

    def on_session_stopped(self, profile):
        entry = self._sessions.get(profile)
        if entry:
            entry["ready"] = False
            entry["starting"] = False
            entry["stopping"] = False
        self.load_accounts()

    def _remove_session(self, profile):
        entry = self._sessions.pop(profile, None)
        if entry:
            browser_pool.unregister_worker(profile, entry["worker"])
        self.load_accounts()

    def shutdown_sessions(self):
        entries = list(self._sessions.values())
        for entry in entries:
            entry["stopping"] = True
            entry["worker"].cancel_event.set()
            entry["worker"].shutting_down = True
            entry["worker"].shutdown_requested.emit()

        for entry in entries:
            entry["thread"].wait(70000)
    
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

    def add_facebook(self):
        try:
            account = self.account_service.create_pending_facebook()
            self.load_accounts()
            self.login_account(account)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Không thể thêm Facebook",
                str(exc),
            )

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
