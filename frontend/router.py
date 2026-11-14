from typing import List, Tuple, Type, Optional
from PySide6.QtWidgets import QWidget

# Import các trang đã hoàn thiện
from frontend.pages.dashboard import DashboardPage
from frontend.pages.accounts import AccountsPage
from frontend.pages.groups import GroupsPage
from frontend.pages.comment_page import CommentPage
from frontend.pages.posts import PostPage
from frontend.pages.customers import CustomersPage
from frontend.pages.reports import ReportsPage
from frontend.pages.messenger import MessengerPage

# Định nghĩa kiểu dữ liệu cho một Page (Giúp code tường minh hơn)
# Tuple gồm: (Tên trang trên Sidebar, Class của Widget hoặc None)
PageConfig = Tuple[str, Optional[Type[QWidget]]]

PAGES: List[PageConfig] = [
    # ==========================
    # OVERVIEW (Tổng quan)
    # ==========================
    ("🏠 Dashboard", DashboardPage),
    
    # ==========================
    # MANAGEMENT (Quản lý)
    # ==========================
    ("👤 Accounts", AccountsPage),
    ("👥 Groups", GroupsPage),
    ("📰 Posts", PostPage),
    ("💬 Comment", CommentPage),
    
    # ==========================
    # ENGAGEMENT (Tương tác)
    # ==========================
    ("💬 Customers", CustomersPage),
    ("📨 Messenger", MessengerPage),
    
    # ==========================
    # SYSTEM & SETTINGS (Hệ thống)
    # ==========================
    ("🤖 AI Engine", None),
    ("📊 Reports", ReportsPage),
    ("⚙ Settings", None),
]
