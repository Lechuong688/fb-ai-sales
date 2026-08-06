from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
    QFrame,
    QGraphicsDropShadowEffect
)
from PySide6.QtGui import QColor

class LoadingWidget(QWidget):
    def __init__(self, parent=None):
        # Truyền parent vào để Overlay biết nó cần che phủ cửa sổ nào
        super().__init__(parent)

        self.setObjectName("loadingOverlay")

        # Layout của Overlay chứa cái Box ở giữa
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignCenter)

        # ===== Hộp trắng chứa nội dung (Loading Box) =====
        self.box = QFrame()
        self.box.setObjectName("loadingBox")
        self.box.setFixedSize(300, 160) # Kích thước cố định cho hộp

        # Thêm hiệu ứng đổ bóng cho Box
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setXOffset(0)
        shadow.setYOffset(10)
        shadow.setColor(QColor(0, 0, 0, 40))
        self.box.setGraphicsEffect(shadow)

        # Layout bên trong Box
        box_layout = QVBoxLayout(self.box)
        box_layout.setAlignment(Qt.AlignCenter)
        box_layout.setSpacing(12)
        box_layout.setContentsMargins(24, 24, 24, 24)

        # Nội dung bên trong
        self.title = QLabel("Loading...")
        self.title.setObjectName("loadingTitle")
        self.title.setAlignment(Qt.AlignCenter)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)      # Chế độ chạy vô tận (Indeterminate)
        self.progress.setFixedHeight(8)   # Ép chiều cao giống CSS
        self.progress.setTextVisible(False)

        self.message = QLabel("Vui lòng chờ trong giây lát...")
        self.message.setObjectName("loadingMessage")
        self.message.setAlignment(Qt.AlignCenter)

        # Thêm các thành phần vào Box
        box_layout.addWidget(self.title)
        box_layout.addWidget(self.progress)
        box_layout.addWidget(self.message)

        # Thêm Box vào giữa màn hình Overlay
        main_layout.addWidget(self.box)

        self.hide()

    def show_loading(self, title="Loading...", message="Vui lòng chờ trong giây lát..."):
        """
        Cập nhật cả tiêu đề và tin nhắn khi hiển thị
        """
        self.title.setText(title)
        self.message.setText(message)
        
        # Đảm bảo Overlay che phủ toàn bộ parent widget
        if self.parent():
            self.resize(self.parent().size())
            
        self.show()
        self.raise_() # Đẩy widget này lên lớp cao nhất

    def hide_loading(self):
        self.hide()