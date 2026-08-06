import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from frontend.widgets.sidebar import Sidebar
from frontend.widgets.header import Header
from frontend.pages.dashboard import DashboardPage
from frontend.pages.accounts import AccountsPage
from frontend.pages.groups import GroupsPage
from frontend.router import PAGES
from frontend.widgets.status_bar import StatusBar

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.pages = {}
        self.setWindowTitle("Facebook AI Sales")
        
        # Kích thước chuẩn cho ứng dụng dạng Dashboard
        self.resize(1400, 850)

        self.build_ui()
        
        # Tự động load và áp dụng toàn bộ giao diện từ file theme.qss
        self.load_theme()

    def load_theme(self):
        """Hàm đọc file theme.qss và áp dụng cho toàn MainWindow"""
        # Xác định đường dẫn file theme.qss (giả định nằm cùng cấp với thư mục chạy app)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Bạn có thể điều chỉnh đường dẫn tương đối tùy theo cấu trúc thư mục của dự án
        # Ví dụ: os.path.join(current_dir, "..", "theme.qss")
        qss_path = os.path.join(current_dir, "theme.qss") 
        
        try:
            with open(qss_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        except FileNotFoundError:
            print(f"[CẢNH BÁO] Không tìm thấy file giao diện tại: {qss_path}")

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
        # Đặt tên object để QSS tô nền xám nhạt cho khu vực này
        content.setObjectName("mainContent")

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
                page = page_class()
                self.pages[page_class.__name__] = page
                self.stack.addWidget(page)

        content_layout.addWidget(self.stack)

        self.status_bar = StatusBar()
        content_layout.addWidget(self.status_bar)

        layout.addWidget(content)

        # Kết nối sự kiện chuyển trang
        self.sidebar.currentRowChanged.connect(self.change_page)
        self.sidebar.setCurrentRow(0)

    def change_page(self, index):
        self.stack.setCurrentIndex(index)

        item = self.sidebar.currentItem()

        if item:
            page_name = item.text()
            
            # Cập nhật Breadcrumb ở Header
            self.header.breadcrumb.set_page(page_name)
            
            # Cập nhật Status Bar phía dưới cùng
            self.status_bar.set_status(f"Đã chuyển sang: {page_name}")

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