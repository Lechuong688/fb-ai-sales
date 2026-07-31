from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class ActivityWidget(QFrame):
    def __init__(self):
        super().__init__()

        self.setObjectName("activityWidget")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel("Recent Activity")
        title.setObjectName("sectionTitle")

        layout.addWidget(title)

        logs = [
            "✓ Đăng nhập Facebook",
            "✓ Quét nhóm Bosch",
            "✓ Phát hiện khách hàng mới",
            "✓ AI phân loại khách tiềm năng"
        ]

        for log in logs:
            layout.addWidget(QLabel(log))

        layout.addStretch()