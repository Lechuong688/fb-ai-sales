from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
)

class Toolbar(QWidget):
    searchChanged = Signal(str)

    def __init__(self, buttons=None, has_search=True):
        super().__init__()

        self.setObjectName("toolbar")

        self.layout = QHBoxLayout(self)
        # Giữ margin đáy là 12px để tạo khoảng cách với Table/Content phía dưới
        self.layout.setContentsMargins(0, 0, 0, 12)
        self.layout.setSpacing(12) # Tăng spacing lên 12 cho thoáng

        self.buttons = []

        self.search = None
        # ================= Buttons =================
        if buttons:
            for text, callback in buttons:
                self.add_button(text, callback)

        self.layout.addStretch()

        # ================= Search =================
        
        if has_search:
            self.search = QLineEdit()
            self.search.setObjectName("toolbarSearch")
            self.search.setPlaceholderText("🔍 Tìm kiếm...")
            self.search.setFixedWidth(260)
            
            # Ép chiều cao 36px cho vừa khớp với form dáng viên thuốc trong CSS
            self.search.setFixedHeight(36)

            self.search.textChanged.connect(self.searchChanged.emit)

            self.layout.addWidget(self.search)

    # ============================================
    # Add button
    # ============================================
    def add_button(self, text, callback):
        button = QPushButton(text)
        button.setObjectName("toolbarButton")
        
        # Dùng setFixedHeight thay vì Minimum để nút luôn đều đẹp với khung tìm kiếm
        button.setFixedHeight(36)
        
        # Đổi hình chuột thành bàn tay khi lướt qua (giống Web)
        button.setCursor(Qt.PointingHandCursor)

        if callback:
            button.clicked.connect(callback)

        # Chèn nút bấm vào trước thanh Stretch để nó luôn nằm bên trái
        # (Vì thanh Stretch nằm ở cuối list buttons)
        index_to_insert = self.layout.count() - 2 if self.search else self.layout.count() - 1
        
        # Sửa lại cơ chế add widget để tương thích nếu gọi add_button sau khi khởi tạo
        if self.layout.count() > 1:
            self.layout.insertWidget(len(self.buttons), button)
        else:
            self.layout.addWidget(button)

        self.buttons.append(button)
        return button

    # ============================================
    # Search
    # ============================================
    def text(self):
        if self.search:
            return self.search.text()
        return ""

    def clear_search(self):
        if self.search:
            self.search.clear()

    def set_search_visible(self, visible: bool):
        if self.search:
            self.search.setVisible(visible)