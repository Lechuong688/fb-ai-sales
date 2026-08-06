from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QGraphicsDropShadowEffect
)
from PySide6.QtGui import QColor

# Giả định import signals của bạn
from backend.signals import signals

class SystemStatus(QFrame):
    def __init__(self):
        super().__init__()

        self.setObjectName("card")

        # 1. Hiệu ứng đổ bóng cho Card
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 15))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("System Status")
        title.setObjectName("cardTitle")
        layout.addWidget(title)

        # 2. Layout chứa danh sách trạng thái
        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(12)
        layout.addLayout(self.rows_layout)

        # Khởi tạo các hàng bằng hàm hỗ trợ
        self.fb_icon, self.fb_val = self._add_row("Facebook")
        self.browser_icon, self.browser_val = self._add_row("Browser")
        self.ai_icon, self.ai_val = self._add_row("AI Engine")
        self.db_icon, self.db_val = self._add_row("Database")

        layout.addStretch()

        # Set trạng thái mặc định ban đầu
        self.set_facebook(False)
        self.set_browser(False)
        self.set_ai("Idle")
        self.set_database(False)

        # Kết nối Signals
        if hasattr(signals, "facebook_status"):
            signals.facebook_status.connect(self.set_facebook)
        if hasattr(signals, "browser_status"):
            signals.browser_status.connect(self.set_browser)
        if hasattr(signals, "database_status"):
            signals.database_status.connect(self.set_database)

    # ==========================================
    # CÁC HÀM HỖ TRỢ (UI Helpers)
    # ==========================================

    def _add_row(self, name: str):
        """Tạo một hàng mới gồm: [Icon] [Tên] --- khoảng trống --- [Giá trị]"""
        row = QHBoxLayout()

        icon_lbl = QLabel()
        icon_lbl.setFixedWidth(24) # Giữ cho các Icon luôn thẳng cột dọc

        name_lbl = QLabel(name)
        name_lbl.setObjectName("statusName")

        val_lbl = QLabel()
        val_lbl.setObjectName("statusValue")
        val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter) # Căn lề phải

        row.addWidget(icon_lbl)
        row.addWidget(name_lbl)
        row.addStretch() # Đẩy val_lbl sát mép phải
        row.addWidget(val_lbl)

        self.rows_layout.addLayout(row)
        return icon_lbl, val_lbl

    def _update_state(self, icon_lbl, val_lbl, icon: str, text: str, state: str):
        """Hàm cập nhật text và màu sắc CSS dựa theo biến state"""
        icon_lbl.setText(icon)
        val_lbl.setText(text)
        
        # Đổi thuộc tính để CSS tự load màu
        val_lbl.setProperty("state", state)
        val_lbl.style().unpolish(val_lbl)
        val_lbl.style().polish(val_lbl)

    # ==========================================
    # CẬP NHẬT TRẠNG THÁI
    # ==========================================

    def set_facebook(self, connected: bool):
        if connected:
            self._update_state(self.fb_icon, self.fb_val, "🟢", "Connected", "ok")
        else:
            self._update_state(self.fb_icon, self.fb_val, "🔴", "Offline", "error")

    def set_browser(self, ready: bool):
        if ready:
            self._update_state(self.browser_icon, self.browser_val, "🟢", "Ready", "ok")
        else:
            self._update_state(self.browser_icon, self.browser_val, "🔴", "Closed", "error")

    def set_ai(self, status: str):
        # AI có nhiều trạng thái nên ta dựa vào text để xác định màu
        state_color = "idle"
        icon = "🤖"
        if status.lower() in ["running", "processing"]:
            state_color = "ok"
            icon = "🟢"
            
        self._update_state(self.ai_icon, self.ai_val, icon, status, state_color)

    def set_database(self, connected: bool):
        if connected:
            self._update_state(self.db_icon, self.db_val, "🟢", "Connected", "ok")
        else:
            self._update_state(self.db_icon, self.db_val, "🟡", "Waiting", "warning")