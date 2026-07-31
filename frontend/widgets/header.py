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

        self.setFixedHeight(70)
        self.setObjectName("header")

        # Layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)

        # Logo / Title
        self.title = QLabel("Facebook AI Sales")
        self.title.setStyleSheet("""
            font-size:22px;
            font-weight:700;
        """)

        # Breadcrumb
        self.breadcrumb = Breadcrumb()

        # Status
        self.status_label = QLabel("🟢 Running")
        self.status_label.setAlignment(Qt.AlignRight)
        self.status_label.setStyleSheet("""
            font-size:14px;
        """)

        # Layout
        left = QHBoxLayout()
        left.addWidget(self.title)
        left.addSpacing(20)
        left.addWidget(self.breadcrumb)

        layout.addLayout(left)
        layout.addStretch()
        layout.addWidget(self.status_label)

    def set_status(self, text):
        self.status_label.setText(text)