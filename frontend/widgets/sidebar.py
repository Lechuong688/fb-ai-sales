from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
)

from frontend.router import PAGES
from frontend.widgets.icons import navigation_icon

NAVIGATION = [
    ("Tổng quan", "grid"),
    ("Tài khoản Facebook", "account"),
    ("Nhóm Facebook", "groups"),
    ("Đăng bài", "edit"),
    ("Tìm khách hàng", "search"),
    ("Khách hàng tiềm năng", "contacts"),
    ("Kết nối & chăm sóc", "message"),
    ("Trợ lý AI", "sparkles"),
    ("Báo cáo", "chart"),
    ("Cài đặt", "settings"),
]

class Sidebar(QListWidget):
    def __init__(self):
        super().__init__()

        self.setObjectName("sidebar")

        # Tăng chiều rộng lên một chút (240-260 là tiêu chuẩn của các Web Dashboard)
        self.setFixedWidth(232)
        self.setIconSize(QSize(18, 18))

        # Khoảng cách giữa các menu item
        self.setSpacing(4)

        self.setFocusPolicy(Qt.NoFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        for index, (title, page_class) in enumerate(PAGES):
            # Gợi ý: Nếu trong PAGES bạn cấu hình title có chứa Emoji (VD: "🏠 Trang chủ") 
            # thì Sidebar sẽ tự động có icon rất đẹp mà không cần code phức tạp.
            label, icon_name = NAVIGATION[index]
            item = QListWidgetItem(navigation_icon(icon_name), label)
            item.setData(Qt.UserRole, title)
            item.setToolTip(label + (" · Đang phát triển" if page_class is None else ""))

            # Ép chiều cao cố định (ví dụ 44px) cho từng item. 
            # Giúp các nút bấm to, dễ click và trông cân đối hơn.
            item.setSizeHint(QSize(0, 44))

            self.addItem(item)
            
        # Tự động chọn (highlight) trang đầu tiên khi khởi động ứng dụng
        if self.count() > 0:
            self.setCurrentRow(0)

        self.compact = False
        self.currentRowChanged.connect(self._update_icons)
        self._update_icons(self.currentRow())

    def _update_icons(self, selected):
        for index in range(self.count()):
            self.item(index).setIcon(navigation_icon(NAVIGATION[index][1], color="#2563eb" if index == selected else "#718198"))

    def set_compact(self, compact):
        if self.compact == compact:
            return
        self.compact = compact
        self.setProperty("compact", compact)
        self.setFixedWidth(72 if compact else 232)
        self.style().unpolish(self)
        self.style().polish(self)
        for row in range(self.count()):
            item = self.item(row)
            item.setText("" if compact else NAVIGATION[row][0])
            item.setTextAlignment(Qt.AlignCenter if compact else Qt.AlignLeft | Qt.AlignVCenter)
