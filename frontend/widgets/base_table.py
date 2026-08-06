from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
)

class BaseTable(QTableWidget):
    def __init__(self):
        super().__init__()

        # Đặt tên object để gọi trong file theme.qss
        self.setObjectName("baseTable")

        # ===== Basic =====
        self.setAlternatingRowColors(False)
        self.setShowGrid(False) # Đã ẩn lưới mặc định, QSS sẽ vẽ lại đường kẻ ngang
        self.setWordWrap(False)
        self.setCornerButtonEnabled(False)

        # ===== Selection =====
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setFocusPolicy(Qt.NoFocus) # Rất tốt để bỏ focus ring mặc định

        # ===== Header =====
        self.verticalHeader().hide()

        header = self.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setMinimumHeight(42)
        
        # Thêm padding nhẹ cho header giống trong QSS
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # ===== Rows =====
        self.verticalHeader().setDefaultSectionSize(44)

        # ===== Sorting =====
        self.setSortingEnabled(True)

        # (Tùy chọn) Ẩn viền focus của header nếu có
        header.setHighlightSections(False)