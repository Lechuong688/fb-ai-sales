from PySide6.QtCore import Qt
from frontend.widgets.sidebar import Sidebar
from frontend.widgets.header import Header
from frontend.pages.dashboard import DashboardPage
from frontend.pages.accounts import AccountsPage
from PySide6.QtWidgets import (
    QLabel,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Facebook AI Sales")
        self.resize(1400, 850)

        self.build_ui()

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)

        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

    # ================= Sidebar =================

        self.sidebar = Sidebar()
        layout.addWidget(self.sidebar)

    # ================= Content =================

        content = QWidget()

        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        header = Header()
        content_layout.addWidget(header)

        self.stack = QStackedWidget()

        self.stack.addWidget(DashboardPage())
        self.stack.addWidget(AccountsPage())
        self.stack.addWidget(self.create_page("Groups"))
        self.stack.addWidget(self.create_page("Posts"))
        self.stack.addWidget(self.create_page("Customers"))
        self.stack.addWidget(self.create_page("AI"))
        self.stack.addWidget(self.create_page("Reports"))
        self.stack.addWidget(self.create_page("Settings"))

        content_layout.addWidget(self.stack)

        layout.addWidget(content)

        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.sidebar.setCurrentRow(0)

    def create_page(self, title):
        page = QWidget()

        layout = QVBoxLayout(page)

        label = QLabel(title)
        label.setAlignment(Qt.AlignCenter)

        label.setStyleSheet("""
            font-size:30px;
            font-weight:bold;
        """)

        layout.addStretch()
        layout.addWidget(label)
        layout.addStretch()

        return page