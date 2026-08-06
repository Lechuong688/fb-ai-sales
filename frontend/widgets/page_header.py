from PySide6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
)

class PageHeader(QWidget):
    def __init__(self, title: str, description: str = ""):
        super().__init__()

        layout = QVBoxLayout(self)
        
        # Tăng margin dưới lên 24px để tạo khoảng cách rộng rãi với phần thân trang
        layout.setContentsMargins(0, 0, 0, 24)
        
        # Tăng khoảng cách giữa Title và Description lên một chút cho dễ thở
        layout.setSpacing(6)

        self.title = QLabel(title)
        self.title.setObjectName("pageTitle")

        self.description = QLabel(description)
        self.description.setObjectName("pageDescription")
        
        # Bật tính năng tự động xuống dòng phòng trường hợp đoạn mô tả quá dài
        self.description.setWordWrap(True)

        # Luôn luôn add cả 2 widget vào layout để giữ cấu trúc
        layout.addWidget(self.title)
        layout.addWidget(self.description)

        # Nếu khởi tạo không có description, ta ẩn nó đi
        self.description.setVisible(bool(description))

    def set_title(self, text: str):
        self.title.setText(text)

    def set_description(self, text: str):
        self.description.setText(text)
        
        # Sẽ tự động hiện nếu text có nội dung, ẩn nếu text rỗng ("")
        self.description.setVisible(bool(text))