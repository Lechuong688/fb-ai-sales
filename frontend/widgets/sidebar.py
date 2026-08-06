from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
)

from frontend.router import PAGES

class Sidebar(QListWidget):
    def __init__(self):
        super().__init__()

        self.setObjectName("sidebar")

        # Tăng chiều rộng lên một chút (240-260 là tiêu chuẩn của các Web Dashboard)
        self.setFixedWidth(240)

        # Khoảng cách giữa các menu item
        self.setSpacing(4)

        self.setFocusPolicy(Qt.NoFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        for title, _ in PAGES:
            # Gợi ý: Nếu trong PAGES bạn cấu hình title có chứa Emoji (VD: "🏠 Trang chủ") 
            # thì Sidebar sẽ tự động có icon rất đẹp mà không cần code phức tạp.
            item = QListWidgetItem(title)

            # Ép chiều cao cố định (ví dụ 44px) cho từng item. 
            # Giúp các nút bấm to, dễ click và trông cân đối hơn.
            item.setSizeHint(QSize(0, 44))

            self.addItem(item)
            
        # Tự động chọn (highlight) trang đầu tiên khi khởi động ứng dụng
        if self.count() > 0:
            self.setCurrentRow(0)