from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
)


class ActivityWidget(QFrame):

    def __init__(self):
        super().__init__()

        self.setObjectName("card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

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

            icon_label = QLabel(icon)
            icon_label.setFixedWidth(28)

            text_label = QLabel(text)
            text_label.setObjectName("activityText")

            row.addWidget(icon_label)
            row.addWidget(text_label)
            row.addStretch()

            layout.addLayout(row)

        layout.addStretch()