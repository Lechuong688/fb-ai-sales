from typing import List, Tuple, Type, Optional
from PySide6.QtWidgets import QWidget

# Import các trang đã hoàn thiện
from frontend.pages.dashboard import DashboardPage
from frontend.pages.accounts import AccountsPage
from frontend.pages.groups import GroupsPage

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
    ("📰 Posts", None),
    
    # ==========================
    # ENGAGEMENT (Tương tác)
    # ==========================
    ("💬 Customers", None),
    ("📨 Messenger", None),
    
    # ==========================
    # SYSTEM & SETTINGS (Hệ thống)
    # ==========================
    ("🤖 AI Engine", None),
    ("📊 Reports", None),
    ("⚙ Settings", None),
]