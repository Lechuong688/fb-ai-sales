from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QVBoxLayout,
    QGraphicsDropShadowEffect
)
from PySide6.QtGui import QColor

class Card(QFrame):
    def __init__(self, title: str = ""):
        super().__init__()

        self.setObjectName("card")

        # 1. Thêm hiệu ứng đổ bóng mặc định cho mọi Card
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 15))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        # Tăng margin lên 24 giống ActivityWidget để không gian rộng rãi hơn
        layout.setContentsMargins(24, 24, 24, 24) 
        layout.setSpacing(16)

        self.title = QLabel(title)
        self.title.setObjectName("cardTitle")
        layout.addWidget(self.title)
        
        # 2. Nếu khởi tạo không truyền title, tự động ẩn đi để không tốn diện tích
        if not title:
            self.title.hide()

        self.body = QVBoxLayout()
        self.body.setSpacing(12)

        layout.addLayout(self.body)
        layout.addStretch()

    def add_widget(self, widget):
        self.body.addWidget(widget)

    def add_layout(self, layout):
        """Hàm bổ sung: Cho phép add cả một layout vào body thay vì chỉ widget"""
        self.body.addLayout(layout)

    def clear(self):
        while self.body.count():
            item = self.body.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            # Xử lý dọn dẹp nếu item bên trong là một layout con
            elif item.layout():
                self.clear_layout(item.layout())

    def clear_layout(self, layout):
        """Hàm đệ quy để xóa sạch các widget nằm trong layout con"""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            elif item.layout():
                self.clear_layout(item.layout())
        layout.deleteLater()

    def set_title(self, text):
        self.title.setText(text)
        # Hiện lại title nếu trước đó bị ẩn
        if text:
            self.title.show()
        else:
            self.title.hide()