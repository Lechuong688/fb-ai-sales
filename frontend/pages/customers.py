import csv
from datetime import datetime, timezone
import math

from PySide6.QtCore import Qt, QTimer, QUrl, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QMessageBox,
    QPlainTextEdit, QPushButton, QSplitter, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget,
)

from backend.database.repositories.lead_repository import WORKFLOW_STATUSES, REVIEW_STATUSES
from backend.facebook.parsers.post_date import VIETNAM_TZ
from backend.services.lead_service import LeadService, real_post_url
from backend.signals import signals
from frontend.layouts.flow_layout import FlowLayout
from frontend.pages.base_page import BasePage
from frontend.widgets.base_table import BaseTable


def display_date(value):
    if not value:
        return "Chưa rõ"
    try:
        date = datetime.fromisoformat(value) if isinstance(value, str) else value
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return date.astimezone(VIETNAM_TZ).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return str(value)


class CustomersPage(BasePage):
    """Local lead follow-up and reply review. No posting or messaging actions."""

    PAGE_SIZE = 100

    def __init__(self, service=None):
        super().__init__(
            title="Khách hàng tiềm năng",
            description="Mỗi hồ sơ là một bài có nhu cầu mua đã tìm được. Lưu ghi chú, theo dõi và duyệt bản nháp trên máy; chưa gửi bình luận.",
            buttons=[("↻ Làm mới", self.reload), ("Xuất danh sách CSV", self.export_csv)],
        )
        self.service = service or LeadService()
        self._loading = False
        self._dirty = False
        self._current = None
        self._page = 0
        self._total = 0

        filters = FlowLayout()
        self.status_filter = QComboBox()
        self.review_filter = QComboBox()
        self.status_filter.addItem("Tất cả trạng thái", "")
        self.review_filter.addItem("Tất cả bản nháp", "")
        for code, text in WORKFLOW_STATUSES.items():
            self.status_filter.addItem(text, code)
        for code, text in REVIEW_STATUSES.items():
            self.review_filter.addItem(text, code)
        filters.addWidget(self.status_filter)
        filters.addWidget(self.review_filter)
        self.layout.addLayout(filters)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.layout.addWidget(self.summary_label)

        self.table = BaseTable()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Tác giả", "Sản phẩm", "Nhóm", "Ngày đăng", "Theo dõi", "Bản nháp"])
        self.table.setWordWrap(True)
        self.table.verticalHeader().setDefaultSectionSize(64)
        self.table.setMinimumHeight(220)

        list_panel = QWidget()
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.addWidget(self.table, 1)
        pager = QHBoxLayout()
        self.previous_button = QPushButton("← Trang trước")
        self.next_button = QPushButton("Trang sau →")
        self.page_label = QLabel()
        pager.addWidget(self.previous_button)
        pager.addWidget(self.page_label, 1)
        pager.addWidget(self.next_button)
        list_layout.addLayout(pager)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(8, 0, 0, 0)
        self.detail_title = QLabel("Chọn một hồ sơ để xem")
        self.detail_title.setWordWrap(True)
        self.source_label = QLabel()
        self.source_label.setWordWrap(True)
        self.rule_label = QLabel()
        self.rule_label.setWordWrap(True)
        for label in (self.detail_title, self.source_label, self.rule_label):
            label.setTextFormat(Qt.PlainText)
        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.source_label)
        detail_layout.addWidget(self.rule_label)
        self.post_text = QPlainTextEdit()
        self.post_text.setReadOnly(True)
        self.post_text.setMaximumHeight(150)
        self.post_text.setPlaceholderText("Nội dung bài gốc")
        detail_layout.addWidget(self.post_text)
        detail_layout.addWidget(QLabel("Bình luận dự kiến — chỉ lưu trên máy"))
        self.draft_input = QTextEdit()
        self.draft_input.setMinimumHeight(100)
        detail_layout.addWidget(self.draft_input, 1)
        self.notes_input = QPlainTextEdit()
        self.notes_input.setMaximumHeight(100)
        self.notes_input.setPlaceholderText("Ghi chú chăm sóc, thời điểm cần liên hệ lại...")
        detail_layout.addWidget(self.notes_input)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.workflow_combo = QComboBox()
        for code, label in WORKFLOW_STATUSES.items():
            self.workflow_combo.addItem(label, code)
        self.review_label = QLabel()
        self.review_label.setWordWrap(True)
        form.addRow("Trạng thái theo dõi", self.workflow_combo)
        form.addRow("Duyệt bản nháp", self.review_label)
        detail_layout.addLayout(form)

        actions = FlowLayout()
        self.save_button = QPushButton("Lưu thay đổi")
        self.approve_button = QPushButton("Duyệt nội dung này")
        self.reject_button = QPushButton("Không dùng bản nháp")
        self.reset_button = QPushButton("Hoàn tác / Nạp lại")
        self.open_button = QPushButton("Mở bài gốc")
        self.open_button.setToolTip("Mở bằng trình duyệt mặc định. Không gửi bình luận.")
        for button in (self.save_button, self.approve_button, self.reject_button, self.reset_button, self.open_button):
            actions.addWidget(button)
        detail_layout.addLayout(actions)
        self.status_label = QLabel("Kết quả quét thật sẽ tự lưu vào đây; tình huống mẫu offline không được lưu.")
        self.status_label.setWordWrap(True)
        detail_layout.addWidget(self.status_label)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(list_panel)
        self.splitter.addWidget(detail)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([650, 550])
        self.splitter.setMinimumHeight(600)
        self.set_content(self.splitter)

        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(250)
        self.search_timer.timeout.connect(self._filter_changed)
        self.toolbar.searchChanged.connect(lambda _text: self.search_timer.start())
        self.status_filter.currentIndexChanged.connect(self._filter_changed)
        self.review_filter.currentIndexChanged.connect(self._filter_changed)
        self.previous_button.clicked.connect(lambda: self._change_page(-1))
        self.next_button.clicked.connect(lambda: self._change_page(1))
        self.table.currentCellChanged.connect(self._select_row)
        self.draft_input.textChanged.connect(self._mark_dirty)
        self.notes_input.textChanged.connect(self._mark_dirty)
        self.workflow_combo.currentIndexChanged.connect(self._mark_dirty)
        self.save_button.clicked.connect(lambda: self.save_current("save"))
        self.approve_button.clicked.connect(lambda: self.save_current("approve"))
        self.reject_button.clicked.connect(lambda: self.save_current("reject"))
        self.reset_button.clicked.connect(self.discard_changes)
        self.open_button.clicked.connect(self.open_post)
        signals.leads_changed.connect(self._on_leads_changed, Qt.QueuedConnection)
        self.reload()

    def set_available_width(self, width):
        orientation = Qt.Vertical if width < 1000 else Qt.Horizontal
        if self.splitter.orientation() != orientation:
            self.splitter.setOrientation(orientation)
            self.splitter.setSizes([360, 760] if orientation == Qt.Vertical else [650, 550])
        self.splitter.setMinimumHeight(1080 if width < 1000 else 600)

    def _filters(self):
        return dict(query=self.toolbar.text(), status=self.status_filter.currentData(), review=self.review_filter.currentData())

    def _filter_changed(self, *_args):
        if not self._dirty:
            self._page = 0
            self.reload()

    def _change_page(self, step):
        if not self._dirty:
            self._page = max(0, self._page + step)
            self.reload()

    def _set_dirty(self, dirty):
        self._dirty = dirty
        self.status_filter.setEnabled(not dirty)
        self.review_filter.setEnabled(not dirty)
        self.toolbar.search.setEnabled(not dirty)
        self.toolbar.buttons[0].setEnabled(not dirty)
        self.previous_button.setEnabled(not dirty and self._page > 0)
        self.next_button.setEnabled(not dirty and (self._page + 1) * self.PAGE_SIZE < self._total)

    def _mark_dirty(self, *_args):
        if self._loading or not self._current:
            return
        self._set_dirty(True)
        self.status_label.setText("Có thay đổi chưa lưu. Lưu hoặc Hoàn tác / Nạp lại trước khi chuyển hồ sơ.")
        if self.draft_input.toPlainText().strip() != self._current["draft_comment"]:
            self.review_label.setText("Nội dung đã sửa — cần duyệt lại sau khi lưu")

    @Slot()
    def _on_leads_changed(self):
        if self._dirty:
            self.status_label.setText("Có dữ liệu mới từ lượt quét. Bản đang sửa được giữ nguyên; lưu hoặc đối chiếu bằng Hoàn tác / Nạp lại.")
        else:
            self.reload()

    def reload(self):
        if self._dirty:
            return
        current_id = self._current["id"] if self._current else None
        try:
            result = self.service.list(**self._filters(), offset=self._page * self.PAGE_SIZE, limit=self.PAGE_SIZE)
            self._total = result["total"]
            if self._page and self._page * self.PAGE_SIZE >= self._total:
                self._page = max(0, math.ceil(self._total / self.PAGE_SIZE) - 1)
                result = self.service.list(**self._filters(), offset=self._page * self.PAGE_SIZE, limit=self.PAGE_SIZE)
            stats = self.service.summary()
        except Exception as exc:
            self.status_label.setText(f"Không tải được khách hàng: {exc}")
            return
        self._loading = True
        self.table.blockSignals(True)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(result["records"]))
        selected_row = 0
        for row, lead in enumerate(result["records"]):
            if lead["id"] == current_id:
                selected_row = row
            values = (lead["author"], lead["product_label"], lead["source_name"] or lead["source_url"],
                      display_date(lead["published_at"]), WORKFLOW_STATUSES[lead["workflow_status"]], REVIEW_STATUSES[lead["review_status"]])
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setData(Qt.UserRole, lead["id"])
                cell.setToolTip(lead["post_text"])
                self.table.setItem(row, column, cell)
        self.table.blockSignals(False)
        self._loading = False
        self.summary_label.setText(f"{stats['total']} hồ sơ đã lưu · {stats['approved']} bản nháp đã duyệt trên máy · {stats['follow_up']} hồ sơ cần theo dõi")
        self.page_label.setText(f"Trang {self._page + 1}/{max(1, math.ceil(self._total / self.PAGE_SIZE))} · {self._total} kết quả")
        self._set_dirty(False)
        if result["records"]:
            self.table.setCurrentCell(selected_row, 0)
            self._load_detail(self.table.item(selected_row, 0).data(Qt.UserRole))
        else:
            self._load_detail(None)

    def _select_row(self, row, *_args):
        if self._loading or row < 0 or not self.table.item(row, 0):
            return
        lead_id = self.table.item(row, 0).data(Qt.UserRole)
        if self._dirty:
            if self._current:
                self._loading = True
                for index in range(self.table.rowCount()):
                    if self.table.item(index, 0).data(Qt.UserRole) == self._current["id"]:
                        self.table.setCurrentCell(index, 0)
                        break
                self._loading = False
            return
        self._load_detail(lead_id)

    def _load_detail(self, lead_id):
        self._loading = True
        self._current = self.service.get(lead_id) if lead_id is not None else None
        lead = self._current
        for widget in (self.draft_input, self.notes_input, self.workflow_combo, self.save_button,
                       self.approve_button, self.reject_button, self.reset_button, self.open_button):
            widget.setEnabled(lead is not None)
        self.detail_title.setText(f"{lead['author']} · {lead['product_label']}" if lead else "Chưa có hồ sơ phù hợp")
        self.source_label.setText(
            f"{lead['source_name'] or lead['source_url']}\nĐăng: {display_date(lead['published_at'])} · Phát hiện bởi: {', '.join(lead['profiles'])}"
            if lead else "Vào Comment để tìm bài; kết quả thật được lưu tự động."
        )
        self.rule_label.setText(f"{lead['rule_name']}\n{lead['rule_reason']}" if lead else "")
        self.post_text.setPlainText(lead["post_text"] if lead else "")
        self.draft_input.setPlainText(lead["draft_comment"] if lead else "")
        self.notes_input.setPlainText(lead["notes"] if lead else "")
        self.workflow_combo.setCurrentIndex(self.workflow_combo.findData(lead["workflow_status"]) if lead else 0)
        self.review_label.setText(REVIEW_STATUSES[lead["review_status"]] if lead else "")
        self._loading = False
        self._set_dirty(False)

    def discard_changes(self):
        self._set_dirty(False)
        self.reload()
        self.status_label.setText("Đã nạp dữ liệu đang lưu trên máy. Chưa gửi bình luận.")

    def save_current(self, action="save"):
        if not self._current:
            return
        try:
            saved = self.service.save_review(
                self._current["id"], self._current["version"], self.draft_input.toPlainText(),
                self.notes_input.toPlainText(), self.workflow_combo.currentData(), action,
            )
        except Exception as exc:
            self.status_label.setText(str(exc))
            return
        self._current = saved
        self._set_dirty(False)
        self.reload()
        self.status_label.setText("Đã lưu trên máy. Duyệt bản nháp không gửi bình luận lên Facebook.")

    def open_post(self):
        if self._current and real_post_url(self._current["post_url"]):
            QDesktopServices.openUrl(QUrl(self._current["post_url"]))

    def confirm_close(self):
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self, "Thay đổi chưa lưu", "Lưu thay đổi trong hồ sơ khách hàng trước khi thoát?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save,
        )
        if answer == QMessageBox.Save:
            self.save_current("save")
            return not self._dirty
        return answer == QMessageBox.Discard

    def export_csv(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Xuất khách hàng theo bộ lọc", "khach-hang-tiem-nang.csv", "CSV (*.csv)")
        if not filename:
            return
        try:
            records = self.service.list(**self._filters(), limit=None)["records"]
            with open(filename, "w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Tác giả", "Bài viết", "URL", "Nhóm", "Ngày đăng", "Sản phẩm", "Mã hàng", "Nick phát hiện", "Theo dõi", "Bản nháp", "Nội dung dự kiến", "Ghi chú"])
                for lead in records:
                    values = [lead["author"], lead["post_text"], lead["post_url"], lead["source_name"], display_date(lead["published_at"]),
                              lead["product_label"], ", ".join(lead["skus"]), ", ".join(lead["profiles"]), WORKFLOW_STATUSES[lead["workflow_status"]],
                              REVIEW_STATUSES[lead["review_status"]], lead["draft_comment"], lead["notes"]]
                    writer.writerow(["'" + str(value) if str(value).lstrip().startswith(("=", "+", "-", "@")) else value for value in values])
        except Exception as exc:
            QMessageBox.warning(self, "Không xuất được danh sách", str(exc))
            return
        self.status_label.setText(f"Đã xuất {len(records)} hồ sơ theo bộ lọc; bản đang sửa chưa lưu không được đưa vào CSV.")
