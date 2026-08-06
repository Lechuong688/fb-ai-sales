from datetime import datetime
from PySide6.QtWidgets import QListWidget, QListWidgetItem
from PySide6.QtGui import QColor

# Giả định import signals của bạn
from backend.signals import signals

class LogWidget(QListWidget):
    MAX_LOGS = 300

    def __init__(self):
        super().__init__()

        self.setObjectName("logWidget")

        # Bật tính năng WordWrap nếu dòng log quá dài (Tùy chọn, rất hữu ích cho Log)
        self.setWordWrap(True) 

        signals.log.connect(self.add_log)

        self.add_log(
            "SYSTEM",
            "Application Started"
        )

    def add_log(
        self,
        category: str,
        message: str = None
    ):
        # Cho phép gọi add_log("text")
        if message is None:
            message = category
            category = "INFO"

        current = datetime.now().strftime("%H:%M:%S")
        text = f"[{current}] [{category.upper()}] {message}"

        # Thay vì self.addItem(text), ta tạo Item để chỉnh màu
        item = QListWidgetItem(text)

        # Đổi màu chữ theo Category
        cat_upper = category.upper()
        if cat_upper == "ERROR":
            item.setForeground(QColor("#dc2626"))  # Đỏ đậm
        elif cat_upper == "WARNING":
            item.setForeground(QColor("#d97706"))  # Cam đậm
        elif cat_upper == "SUCCESS":
            item.setForeground(QColor("#16a34a"))  # Xanh lá đậm
        elif cat_upper == "SYSTEM":
            item.setForeground(QColor("#8b5cf6"))  # Tím
        else:
            item.setForeground(QColor("#475569"))  # Xám (Cho INFO)

        self.addItem(item)

        # Tối ưu hóa: xóa dòng cũ khi vượt quá MAX_LOGS
        while self.count() > self.MAX_LOGS:
            self.takeItem(0)

        # Tự động cuộn xuống dưới cùng
        self.scrollToBottom()

    def info(self, message):
        self.add_log("INFO", message)

    def success(self, message):
        self.add_log("SUCCESS", message)

    def warning(self, message):
        self.add_log("WARNING", message)

    def error(self, message):
        self.add_log("ERROR", message)