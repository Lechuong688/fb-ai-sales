from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QSizePolicy,
    QStyle,
)
from frontend.widgets.breadcrumb import Breadcrumb

class Header(QFrame):
    def __init__(self):
        super().__init__()

        self.setObjectName("header")
        self.setFixedHeight(68)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(15)

        # ===== Breadcrumb =====
        self.breadcrumb = Breadcrumb()
        self.breadcrumb.setMinimumWidth(0)
        self.breadcrumb.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.menu_button = QToolButton()
        self.menu_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowLeft))
        self.menu_button.setToolTip("Thu gọn / mở rộng menu")
        self.menu_button.setAccessibleName("Thu gọn hoặc mở rộng menu")
        self.menu_button.setMinimumSize(36, 36)

        # ===== Status =====
        self.status_label = QLabel("●  Sẵn sàng")
        self.status_label.setObjectName("statusBadge")
        self.status_label.setFixedHeight(28)
        self.status_label.setAlignment(Qt.AlignCenter)
        
        # Đặt thuộc tính động mặc định là "running"
        self.status_label.setProperty("status", "running")

        layout.addWidget(self.menu_button)
        layout.addWidget(self.breadcrumb, 1)
        layout.addWidget(self.status_label)
        self.avatar = QLabel("CS")
        self.avatar.setObjectName("userAvatar")
        self.avatar.setFixedSize(34, 34)
        self.avatar.setAlignment(Qt.AlignCenter)
        self.avatar.setToolTip("Không gian làm việc Facebook AI Sales")
        layout.addWidget(self.avatar)

    def set_status(self, text: str, is_running: bool = True):
        """
        Cập nhật trạng thái và màu sắc của Badge.
        :param text: Text hiển thị (VD: "🔴 Stopped")
        :param is_running: Trạng thái (True = Xanh, False = Đỏ)
        """
        self.status_label.setText(text)
        
        # Cập nhật thuộc tính để CSS tự đổi màu
        status_val = "running" if is_running else "stopped"
        self.status_label.setProperty("status", status_val)
        
        # Gọi lệnh này để PySide6 load lại CSS cho Widget sau khi đổi thuộc tính
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
