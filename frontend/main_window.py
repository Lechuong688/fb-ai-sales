from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QLabel,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QScrollArea,
    QFrame,
    QSizePolicy,
    QStyle,
)

from frontend.widgets.sidebar import Sidebar, NAVIGATION
from frontend.widgets.header import Header
from frontend.pages.dashboard import DashboardPage
from frontend.pages.accounts import AccountsPage
from frontend.pages.groups import GroupsPage
from frontend.router import PAGES
from frontend.widgets.status_bar import StatusBar
from frontend.widgets.icons import navigation_icon


class PageScrollArea(QScrollArea):
    def __init__(self, page):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setMinimumSize(0, 0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.setWidget(page)
        page.setAutoFillBackground(False)
        self.viewport().setObjectName("pageViewport")

    def resizeEvent(self, event):
        page = self.widget()
        if hasattr(page, "set_available_width"):
            page.set_available_width(self.viewport().width())
        super().resizeEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.pages = {}
        self._sidebar_override = None
        self._closing_sessions = False
        self._sessions_closed = False
        self.setWindowTitle("Facebook AI Sales")
        
        # Kích thước chuẩn cho ứng dụng dạng Dashboard
        self.setMinimumSize(760, 520)
        screen = self.screen().availableGeometry()
        self.resize(min(1400, int(screen.width() * 0.9)), min(850, int(screen.height() * 0.9)))

        self.build_ui()
        self._update_sidebar()

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)

        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ================= Sidebar =================
        self.sidebar = Sidebar()
        self.navigation_shell = QFrame()
        self.navigation_shell.setObjectName("navigationShell")
        navigation = QVBoxLayout(self.navigation_shell)
        navigation.setContentsMargins(0, 0, 0, 0)
        navigation.setSpacing(0)
        brand = QWidget()
        brand.setObjectName("brandHeader")
        brand.setFixedHeight(86)
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(20, 16, 12, 12)
        logo = QLabel("f")
        logo.setObjectName("brandMark")
        logo.setFixedSize(34, 36)
        logo.setAlignment(Qt.AlignCenter)
        self.brand_name = QLabel("AI Sales<span style='color:#2563eb'>.</span>")
        self.brand_name.setObjectName("brandName")
        brand_layout.addWidget(logo)
        brand_layout.addWidget(self.brand_name)
        brand_layout.addStretch()
        navigation.addWidget(brand)
        self.navigation_caption = QLabel("KHÔNG GIAN LÀM VIỆC")
        self.navigation_caption.setObjectName("navigationCaption")
        navigation.addWidget(self.navigation_caption)
        navigation.addWidget(self.sidebar, 1)
        self.navigation_footer = QLabel("●  Dữ liệu lưu trên máy\nFacebook AI Sales")
        self.navigation_footer.setObjectName("navigationFooter")
        navigation.addWidget(self.navigation_footer)
        layout.addWidget(self.navigation_shell)

        # ================= Content =================
        content = QWidget()
        # Đặt tên object để QSS tô nền xám nhạt cho khu vực này
        content.setObjectName("mainContent")

        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.header = Header()
        self.header.menu_button.clicked.connect(self.toggle_sidebar)
        content_layout.addWidget(self.header)

        self.stack = QStackedWidget()

        for _, page_class in PAGES:
            if page_class is None:
                self.stack.addWidget(PageScrollArea(self.create_page("Coming Soon")))
            else:
                page = page_class()
                self.pages[page_class.__name__] = page
                self.stack.addWidget(PageScrollArea(page))

        content_layout.addWidget(self.stack)

        self.status_bar = StatusBar()
        content_layout.addWidget(self.status_bar)

        layout.addWidget(content, 1)

        # Kết nối sự kiện chuyển trang
        self.sidebar.currentRowChanged.connect(self.change_page)
        self.sidebar.setCurrentRow(0)
        self.change_page(0)

    def change_page(self, index):
        self.stack.setCurrentIndex(index)

        item = self.sidebar.currentItem()

        if item:
            page_name = NAVIGATION[index][0]
            
            # Cập nhật Breadcrumb ở Header
            self.header.breadcrumb.set_page(page_name)
            
            # Cập nhật Status Bar phía dưới cùng
            self.status_bar.set_status(f"Đã chuyển sang: {page_name}")

    def toggle_sidebar(self):
        self._sidebar_override = not self.sidebar.compact
        self._update_sidebar()

    def _update_sidebar(self):
        compact = self.width() < 1100 if self._sidebar_override is None else self._sidebar_override
        self.sidebar.set_compact(compact)
        self.navigation_shell.setFixedWidth(self.sidebar.width())
        self.brand_name.setVisible(not compact)
        self.navigation_caption.setVisible(not compact)
        self.navigation_footer.setVisible(not compact)
        self.header.menu_button.setIcon(navigation_icon("menu"))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "sidebar"):
            self._update_sidebar()

    def create_page(self, title):
        """Tạo trang giả (Placeholder) cho các tính năng chưa hoàn thiện"""
        page = QWidget()
        layout = QVBoxLayout(page)

        label = QLabel(title)
        label.setAlignment(Qt.AlignCenter)
        
        # Đã loại bỏ self.setStyleSheet inline và thay bằng ObjectName
        label.setObjectName("comingSoonText")

        layout.addStretch()
        layout.addWidget(label)
        layout.addStretch()

        return page

    def closeEvent(self, event):
        comment_page = self.pages.get("CommentPage")
        if comment_page and comment_page._suggestion_thread is not None:
            comment_page._ai_cancel.set()
            self.status_bar.set_status("Đang dừng gợi ý AI. Đợi yêu cầu hiện tại kết thúc rồi đóng ứng dụng lại.")
            event.ignore()
            return
        if self._closing_sessions:
            event.ignore()
            return
        if self._sessions_closed:
            event.accept()
            return
        customers_page = self.pages.get("CustomersPage")
        if customers_page and not customers_page.confirm_close():
            event.ignore()
            return
        outreach_page = self.pages.get("MessengerPage")
        if outreach_page:
            outreach_page.scheduler.enabled = False
            outreach_page.scheduler.timer.stop()
            outreach_page.search_control.stop()
        accounts_page = self.pages.get("AccountsPage")
        if accounts_page:
            accounts_page.shutdown_finished.connect(self._finish_close)
            if not accounts_page.shutdown_sessions():
                self._closing_sessions = True
                self.status_bar.set_status("Đang đóng các phiên Facebook…")
                event.ignore()
                return
        self._sessions_closed = True
        event.accept()

    def _finish_close(self):
        if not self._closing_sessions:
            return
        self._closing_sessions = False
        self._sessions_closed = True
        QTimer.singleShot(0, self.close)
