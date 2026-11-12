import csv
from datetime import datetime, time

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
    QTableWidgetItem,
)

from backend.services.publishing_service import PublishingService
from backend.signals import signals
from backend.utils.text_matching import normalize_text
from frontend.pages.base_page import BasePage
from frontend.widgets.base_table import BaseTable


STATUSES = {"submitted": "Đã gửi", "failed": "Lỗi", "skipped": "Bỏ qua / đã dừng"}
HEADERS = ["Thời gian", "Nick", "Đích", "Trạng thái", "Kết quả", "Nội dung"]


class ReportsPage(BasePage):
    def __init__(self, service=None):
        super().__init__("Báo cáo đăng bài", "Kết quả từng đích, lưu trên máy qua các lần mở ứng dụng.",
                         buttons=[("Làm mới", self.refresh), ("Xuất CSV", self.export_csv)])
        self.service = service or PublishingService()
        self._rows = []
        filters = QHBoxLayout()
        self.status_filter = QComboBox()
        self.status_filter.addItem("Tất cả trạng thái", "")
        for key, label in STATUSES.items():
            self.status_filter.addItem(label, key)
        self.from_date = QDateEdit(QDate.currentDate().addDays(-30))
        self.to_date = QDateEdit(QDate.currentDate())
        for widget in (self.from_date, self.to_date):
            widget.setCalendarPopup(True)
            widget.setDisplayFormat("dd/MM/yyyy")
        filters.addWidget(QLabel("Từ"))
        filters.addWidget(self.from_date)
        filters.addWidget(QLabel("đến"))
        filters.addWidget(self.to_date)
        filters.addWidget(self.status_filter)
        filters.addStretch()
        self.layout.addLayout(filters)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.layout.addWidget(self.summary)
        hint = QLabel("‘Đã gửi’ là đã gửi qua trình đăng bài Facebook; bài trong nhóm có thể còn chờ duyệt.")
        hint.setWordWrap(True)
        hint.setObjectName("pageDescription")
        self.layout.addWidget(hint)
        self.table = BaseTable()
        self.table.setColumnCount(len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setColumnWidth(0, 155)
        self.table.setColumnWidth(2, 250)
        self.table.setColumnWidth(4, 300)
        self.layout.addWidget(self.table)
        self.toolbar.search.setPlaceholderText("Tìm nick, đích, nội dung…")
        self.toolbar.search.textChanged.connect(self.refresh)
        self.status_filter.currentIndexChanged.connect(self.refresh)
        self.from_date.dateChanged.connect(self.refresh)
        self.to_date.dateChanged.connect(self.refresh)
        signals.post_publish_finished.connect(self.refresh, Qt.QueuedConnection)
        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    @staticmethod
    def values(row):
        return [row['created_at'].strftime("%d/%m/%Y %H:%M:%S"), row['profile'],
                "Bảng tin" if row['kind'] == 'feed' else row['target'],
                STATUSES.get(row['status'], row['status']), row['message'], row['content']]

    def refresh(self, *_args):
        if not hasattr(self, 'service'):
            return
        start = datetime.combine(self.from_date.date().toPython(), time.min)
        end = datetime.combine(self.to_date.date().toPython(), time.max)
        query = normalize_text(self.toolbar.search.text())
        status = self.status_filter.currentData()
        try:
            self._rows = [row for row in self.service.history()
                          if start <= row['created_at'] <= end
                          and (not status or row['status'] == status)
                          and query in normalize_text(' '.join(str(v) for v in row.values()))]
        except Exception as exc:
            self.summary.setText(f"Không tải được báo cáo: {exc}")
            self._rows = []
            self.table.setRowCount(0)
            return
        counts = {key: sum(row['status'] == key for row in self._rows) for key in STATUSES}
        self.summary.setText(f"{len(self._rows)} đích · {counts['submitted']} đã gửi · "
                             f"{counts['failed']} lỗi · {counts['skipped']} bỏ qua / đã dừng"
                             + (" · Chưa có kết quả trong bộ lọc này" if not self._rows else ""))
        self.table.setRowCount(len(self._rows))
        was_sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        for index, row in enumerate(self._rows):
            for column, value in enumerate(self.values(row)):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(index, column, item)
        self.table.setSortingEnabled(was_sorting)

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Xuất báo cáo theo bộ lọc", "bao-cao-dang-bai.csv", "CSV (*.csv)")
        if not path:
            return
        def safe(value):
            value = str(value)
            return "'" + value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else value
        try:
            with open(path, 'w', encoding='utf-8-sig', newline='') as handle:
                writer = csv.writer(handle)
                writer.writerow(HEADERS)
                writer.writerows([safe(value) for value in self.values(row)] for row in self._rows)
        except OSError as exc:
            QMessageBox.warning(self, "Không xuất được báo cáo", str(exc))
            return
        signals.status.emit(f"Đã xuất {len(self._rows)} kết quả: {path}")
