from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
)

from frontend.widgets.breadcrumb import Breadcrumb


class Header(QFrame):

    def __init__(self):
        super().__init__()

        self.setObjectName("header")
        self.setFixedHeight(60)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(15)

        # ===== Breadcrumb =====

        self.breadcrumb = Breadcrumb()

        # ===== Status =====

        self.status_label = QLabel("🟢 Running")
        self.status_label.setObjectName("statusBadge")
        self.status_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.breadcrumb)

        layout.addStretch()

        layout.addWidget(self.status_label)

    def set_status(self, text: str):
        self.status_label.setText(text)