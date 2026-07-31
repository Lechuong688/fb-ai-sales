from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PageHeader(QWidget):
    def __init__(self, title: str, description: str = ""):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 20)

        title_label = QLabel(title)
        title_label.setStyleSheet("""
            font-size:28px;
            font-weight:bold;
        """)

        desc = QLabel(description)
        desc.setStyleSheet("""
            color:#9CA3AF;
            font-size:13px;
        """)

        layout.addWidget(title_label)
        layout.addWidget(desc)