from PySide6.QtCore import Qt
from frontend.widgets.sidebar import Sidebar
from frontend.widgets.header import Header
from frontend.pages.dashboard import DashboardPage
from frontend.pages.accounts import AccountsPage
from frontend.pages.groups import GroupsPage
from frontend.router import PAGES
from frontend.widgets.status_bar import StatusBar
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

        self.header = Header()
        content_layout.addWidget(self.header)

        self.stack = QStackedWidget()

        for _, page_class in PAGES:

            if page_class is None:
                self.stack.addWidget(self.create_page("Coming Soon"))
            else:
                self.stack.addWidget(page_class())

        content_layout.addWidget(self.stack)

        self.status_bar = StatusBar()

        content_layout.addWidget(self.status_bar)

        layout.addWidget(content)

        self.sidebar.currentRowChanged.connect(self.change_page)
        self.sidebar.setCurrentRow(0)
    def change_page(self, index):
        self.stack.setCurrentIndex(index)

        item = self.sidebar.currentItem()

        if item:
            page_name = item.text()

            self.header.breadcrumb.set_page(page_name)

            self.status_bar.set_status(f"Đã chuyển sang {page_name}")
        

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