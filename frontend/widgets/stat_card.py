from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QVBoxLayout,
    QGraphicsDropShadowEffect
)
from PySide6.QtGui import QColor

class StatCard(QFrame):
    def __init__(self, title: str, value: str):
        super().__init__()

        self.setObjectName("statCard")
        self.setMinimumHeight(120) # Tăng lên 120px cho cân đối với font chữ to

        # ===== Hiệu ứng đổ bóng (Shadow) =====
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 10)) # Bóng mờ nhẹ hơn Card bình thường một chút
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        # Đổi tên ObjectName thành statTitle để nhận CSS mới
        self.title_label = QLabel(title)
        self.title_label.setObjectName("statTitle")

        # Đổi tên ObjectName thành statValue
        self.value_label = QLabel(value)
        self.value_label.setObjectName("statValue")
        self.value_label.setAlignment(Qt.AlignLeft | Qt.AlignBottom) # Ép xuống dưới cùng

        layout.addWidget(self.title_label)
        layout.addStretch()
        layout.addWidget(self.value_label)

    def set_value(self, value):
        self.value_label.setText(str(value))

    def set_title(self, title):
        self.title_label.setText(title)