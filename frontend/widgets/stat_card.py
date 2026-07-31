from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class StatCard(QFrame):
    def __init__(self, title: str, value: str):
        super().__init__()

        self.setFixedSize(220, 120)
        self.setObjectName("statCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")

        value_label = QLabel(value)
        value_label.setObjectName("cardValue")
        value_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(title_label)
        layout.addStretch()
        layout.addWidget(value_label)