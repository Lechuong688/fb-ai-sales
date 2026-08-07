from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QGraphicsDropShadowEffect
)
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt

class ActivityWidget(QFrame):
    def __init__(self):
        super().__init__()

        self.setObjectName("card")

        # 2. Hiệu ứng đổ bóng (Shadow) vẫn phải code trong Python vì QSS không hỗ trợ DropShadow trực tiếp
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 15))
        self.setGraphicsEffect(shadow)

        # 3. Setup Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Recent Activity")
        title.setObjectName("cardTitle")
        layout.addWidget(title)

        activities = [
            ("🟢", "Đăng nhập Facebook"),
            ("🔍", "Quét nhóm Bosch"),
            ("👤", "Phát hiện khách hàng mới"),
            ("🤖", "AI phân loại khách tiềm năng"),
        ]

        for icon, text in activities:
            row = QHBoxLayout()
            row.setSpacing(10)

            icon_label = QLabel(icon)
            icon_label.setObjectName("iconLabel")
            icon_label.setFixedWidth(28)
            icon_label.setAlignment(Qt.AlignCenter)

            text_label = QLabel(text)
            text_label.setObjectName("activityText")

            row.addWidget(icon_label)
            row.addWidget(text_label)
            row.addStretch()

            layout.addLayout(row)

        layout.addStretch()