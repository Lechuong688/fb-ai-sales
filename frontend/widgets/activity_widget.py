from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from backend.services.comment_history_service import CommentHistoryService
from backend.signals import signals


class ActivityWidget(QFrame):
    MAX_ITEMS = 8

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        self._rows = []

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 15))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Recent Activity")
        title.setObjectName("cardTitle")
        layout.addWidget(title)

        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(9)
        layout.addLayout(self.rows_layout)
        layout.addStretch()

        self._load_recent_comments()
        signals.log.connect(self.add_log)

    def _load_recent_comments(self):
        try:
            records = CommentHistoryService().get_recent(self.MAX_ITEMS)
        except Exception:
            records = []

        for record in reversed(records):
            status = "Bình luận đã gửi" if record["status"] == "sent" else "Bình luận lỗi"
            account = record["account_profile"]
            preview = record["comment_text"].replace("\n", " ").strip()
            preview = preview[:70] + ("…" if len(preview) > 70 else "")
            self._add_activity(
                "💬" if record["status"] == "sent" else "⚠️",
                f"{status} · {account}: {preview}",
                record["created_at"],
            )

    def add_log(self, message):
        text = str(message)
        lowered = text.casefold()
        if "lỗi" in lowered or "error" in lowered:
            icon = "⚠️"
        elif "bình luận" in lowered or "comment" in lowered:
            icon = "💬"
        elif "quét" in lowered or "tìm thấy" in lowered:
            icon = "🔎"
        elif "đăng nhập" in lowered:
            icon = "🟢"
        else:
            icon = "✨"
        self._add_activity(icon, text, datetime.now())

    def _add_activity(self, icon, text, timestamp):
        row_widget = QWidget(self)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(10)

        icon_label = QLabel(icon)
        icon_label.setObjectName("iconLabel")
        icon_label.setFixedWidth(28)
        icon_label.setAlignment(Qt.AlignCenter)

        text_label = QLabel(text)
        text_label.setObjectName("activityText")
        text_label.setWordWrap(True)

        time_label = QLabel(timestamp.strftime("%H:%M"))
        time_label.setObjectName("activityTime")
        time_label.setAlignment(Qt.AlignRight | Qt.AlignTop)

        row_layout.addWidget(icon_label)
        row_layout.addWidget(text_label, 1)
        row_layout.addWidget(time_label)

        self.rows_layout.insertWidget(0, row_widget)
        self._rows.insert(0, row_widget)
        while len(self._rows) > self.MAX_ITEMS:
            old = self._rows.pop()
            self.rows_layout.removeWidget(old)
            old.deleteLater()
