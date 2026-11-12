from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout


class SectionPanel(QFrame):
    """A consistent surface for related form controls."""

    def __init__(self, title, caption="", number=""):
        super().__init__()
        self.setObjectName("sectionPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 18)
        layout.setSpacing(12)
        heading = QHBoxLayout()
        heading.setSpacing(10)
        if number:
            badge = QLabel(number)
            badge.setObjectName("sectionNumber")
            badge.setFixedSize(28, 28)
            badge.setAlignment(Qt.AlignCenter)
            heading.addWidget(badge)
        label = QLabel(title)
        label.setObjectName("sectionTitle")
        heading.addWidget(label)
        heading.addStretch()
        if caption:
            detail = QLabel(caption)
            detail.setObjectName("sectionCaption")
            detail.setWordWrap(False)
            heading.addWidget(detail)
        layout.addLayout(heading)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        layout.addLayout(self.body)
