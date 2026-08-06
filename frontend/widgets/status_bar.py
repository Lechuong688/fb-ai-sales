from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

# Giả định import signals của bạn
from backend.signals import signals

class StatusBar(QLabel):
    def __init__(self):
        super().__init__()

        self.setObjectName("statusBar")

        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # Chốt cứng chiều cao là 36px để thanh trạng thái luôn gọn gàng ở đáy
        self.setFixedHeight(36)

        self.set_status("🟢 Ready")

        signals.status.connect(self.set_status)

    def set_status(self, text: str):
        # Đã cấu hình padding-left trong QSS, nên giờ chỉ cần truyền đúng text
        self.setText(text)