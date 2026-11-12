from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QPushButton,
    QLineEdit,
)
from frontend.layouts.flow_layout import FlowLayout
from frontend.widgets.icons import navigation_icon

class Toolbar(QWidget):
    searchChanged = Signal(str)

    def __init__(self, buttons=None, has_search=True):
        super().__init__()

        self.setObjectName("toolbar")

        self.layout = FlowLayout(self)
        # Giữ margin đáy là 12px để tạo khoảng cách với Table/Content phía dưới
        self.layout.setContentsMargins(0, 0, 0, 12)
        self.layout.setSpacing(8)

        self.buttons = []

        self.search = None
        # ================= Buttons =================
        if buttons:
            for text, callback in buttons:
                self.add_button(text, callback)

        # ================= Search =================
        
        if has_search:
            self.search = QLineEdit()
            self.search.setObjectName("toolbarSearch")
            self.search.setPlaceholderText("🔍 Tìm kiếm...")
            self.search.setMinimumWidth(180)
            self.search.setMaximumWidth(260)
            
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
        button.setProperty(
            "variant",
            "danger" if "tạm dừng" not in text.lower() and any(word in text.lower() for word in ("stop", "dừng", "xóa")) else
            "primary" if not self.buttons else "secondary",
        )
        for prefix, name in (("🔍", "search"), ("📝", "edit"), ("↻", "refresh"),
                             ("🔄", "refresh"), ("＋", "plus"), ("➕", "plus"),
                             ("✨", "sparkles"), ("⚙", "settings"), ("🧪", "sparkles")):
            if text.startswith(prefix):
                button.setText(text[len(prefix):].lstrip("\ufe0f "))
                button.setIcon(navigation_icon(name, "#ffffff" if button.property("variant") == "primary" else "#718198"))
                break
        
        # Dùng setFixedHeight thay vì Minimum để nút luôn đều đẹp với khung tìm kiếm
        button.setFixedHeight(36)
        
        # Đổi hình chuột thành bàn tay khi lướt qua (giống Web)
        button.setCursor(Qt.PointingHandCursor)

        if callback:
            button.clicked.connect(callback)

        # Keep newly added actions before the search field.
        if self.search:
            search_item = self.layout.takeAt(self.layout.count() - 1)
            self.layout.addWidget(button)
            self.layout.addItem(search_item)
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
            self.layout.invalidate()

    def first_button(self):

        if self.buttons:
            return self.buttons[0]

        return None
