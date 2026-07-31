from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QWidget,
)


class Header(QFrame):
    def __init__(self):
        super().__init__()

        self.setFixedHeight(70)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)

        title = QLabel("Facebook AI Sales")

        title.setStyleSheet("""
            font-size:22px;
            font-weight:700;
        """)

        layout.addWidget(title)

        layout.addStretch()

        status = QLabel("🟢 Running")

        status.setAlignment(Qt.AlignRight)

        status.setStyleSheet("""
            font-size:14px;
        """)

        layout.addWidget(status)