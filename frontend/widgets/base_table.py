from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
)


class BaseTable(QTableWidget):

    def __init__(self):
        super().__init__()

        # ===== Basic =====

        self.setAlternatingRowColors(False)

        self.setShowGrid(False)

        self.setWordWrap(False)

        self.setCornerButtonEnabled(False)

        # ===== Selection =====

        self.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )

        self.setSelectionMode(
            QAbstractItemView.SingleSelection
        )

        self.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )

        self.setFocusPolicy(Qt.NoFocus)

        # ===== Header =====

        self.verticalHeader().hide()

        header = self.horizontalHeader()

        header.setStretchLastSection(True)

        header.setSectionResizeMode(
            QHeaderView.Stretch
        )

        header.setMinimumHeight(42)

        header.setDefaultAlignment(
            Qt.AlignLeft | Qt.AlignVCenter
        )

        # ===== Rows =====

        self.verticalHeader().setDefaultSectionSize(44)

        # ===== Sorting =====

        self.setSortingEnabled(True)