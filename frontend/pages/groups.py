from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QTableWidgetItem, QMessageBox

from backend.browser.pool import browser_pool
from backend.services.group_service import GroupService
from backend.signals import signals

from frontend.pages.base_page import BasePage
from frontend.widgets.base_table import BaseTable
from backend.utils.task_control import TaskControl


class GroupsPage(BasePage):

    def __init__(self):

        super().__init__(
            title="Nhóm Facebook",
            description="Xem nhóm đã lưu; bấm Quét nhóm để lấy danh sách mới từ các nick đang đăng nhập.",
            buttons=[
                ("➕ Thêm nhóm", self.add_group),
                ("🔄 Tải lại danh sách đã lưu", self.load_groups),
                ("↻ Quét nhóm nick đang mở", self.scan_open_profiles),
            ]
        )

        self.table = BaseTable()

        self.table.setColumnCount(5)

        self.table.setHorizontalHeaderLabels([
            "Tên nhóm",
            "URL",
            "Thành viên",
            "Loại nhóm",
            "Trạng thái"
        ])

        self.group_service = GroupService()
        self._pending_profiles = set()
        self._groups_paused = False
        self.pause_groups_button = self.toolbar.add_button("Tạm dừng quét", self.toggle_group_pause)
        self.stop_groups_button = self.toolbar.add_button("Dừng quét", self.stop_group_scan)
        self.pause_groups_button.hide()
        self.stop_groups_button.hide()
        signals.groups_synced.connect(self.load_groups, Qt.QueuedConnection)
        signals.groups_synced.connect(self._scan_finished, Qt.QueuedConnection)
        signals.groups_sync_failed.connect(self._scan_failed, Qt.QueuedConnection)
        signals.groups_sync_cancelled.connect(self._scan_cancelled, Qt.QueuedConnection)

        self.load_groups()

        self.set_content(
            self.table
        )

    def scan_open_profiles(self):
        requested = set()
        for session in browser_pool.get_all_sessions():
            if not (session.running and session.logged_in):
                continue
            worker = browser_pool.get_worker(session.profile)
            if not worker or worker.operation_active or session.profile in self._pending_profiles:
                continue
            requested.add(session.profile)
        if not requested:
            QMessageBox.information(
                self, "Chưa có nick sẵn sàng",
                "Mở và đăng nhập nick trong Accounts trước. Nếu nick đang bận, hãy đợi tác vụ kết thúc.",
            )
            return
        self._pending_profiles.update(requested)
        self._update_scan_button()
        for profile in requested:
            worker = browser_pool.get_worker(profile)
            if worker:
                worker.groups_sync_requested.emit()
            else:
                self._scan_failed(profile, "Profile đã đóng.")

    def _update_scan_button(self):
        button = self.toolbar.buttons[2]
        button.setEnabled(not self._pending_profiles)
        button.setText(
            f"Đang quét {len(self._pending_profiles)} nick…"
            if self._pending_profiles else "↻ Quét nhóm nick đang mở"
        )
        for control in (self.pause_groups_button, self.stop_groups_button):
            control.setVisible(bool(self._pending_profiles))
        if not self._pending_profiles:
            self._groups_paused = False
            self.pause_groups_button.setText("Tạm dừng quét")
            self.pause_groups_button.setEnabled(True)
            self.stop_groups_button.setEnabled(True)

    def toggle_group_pause(self):
        self._groups_paused = not self._groups_paused
        for profile in self._pending_profiles:
            worker = browser_pool.get_worker(profile)
            if worker and isinstance(worker.group_control, TaskControl):
                (worker.group_control.pause if self._groups_paused else worker.group_control.resume)()
        self.pause_groups_button.setText("Tiếp tục quét" if self._groups_paused else "Tạm dừng quét")
        signals.status.emit("Đã yêu cầu tạm dừng quét nhóm sau thao tác hiện tại." if self._groups_paused else "Đã tiếp tục quét nhóm.")

    def stop_group_scan(self):
        for profile in self._pending_profiles:
            worker = browser_pool.get_worker(profile)
            if worker and isinstance(worker.group_control, TaskControl):
                worker.group_control.stop()
        self.pause_groups_button.setEnabled(False)
        self.stop_groups_button.setEnabled(False)
        signals.status.emit("Đang dừng quét nhóm; giữ profile mở và dữ liệu đã lưu.")

    @Slot(str)
    def _scan_cancelled(self, profile):
        self._pending_profiles.discard(profile)
        self.load_groups()
        self._update_scan_button()
        signals.status.emit(f"Đã dừng quét nhóm của {profile}.")

    @Slot(str, int)
    def _scan_finished(self, profile, _count):
        self._pending_profiles.discard(profile)
        self._update_scan_button()

    @Slot(str, str)
    def _scan_failed(self, profile, message):
        if profile not in self._pending_profiles:
            return
        self._pending_profiles.discard(profile)
        self._update_scan_button()
        QMessageBox.warning(self, "Không quét được nhóm", f"{profile}: {message}")

    @Slot()
    @Slot(str, int)
    def load_groups(self, *_args):

        groups = self.group_service.get_all()

        sorting_enabled = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)

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
                        if group.member_count and group.member_count != "0"
                        else "Chưa lấy"
                    )
                )
            )

            self.table.setItem(
                row,
                3,
                QTableWidgetItem(
                    group.privacy if group.privacy not in {None, "", "Unknown"} else "Chưa lấy"
                )
            )

            self.table.setItem(
                row,
                4,
                QTableWidgetItem(
                    group.status or "Ready"
                )
            )

        self.table.setSortingEnabled(sorting_enabled)

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

        try:
            self.group_service.create("Facebook Group", url)
        except ValueError as exc:
            QMessageBox.warning(self, "URL nhóm không hợp lệ", str(exc))
            return

        self.load_groups()
