from PySide6.QtWidgets import (
    QLabel,
    QHBoxLayout,
    QGridLayout,
    QBoxLayout,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt, Slot

from backend.signals import signals
from frontend.widgets.activity_widget import ActivityWidget
from frontend.widgets.log_widget import LogWidget
from frontend.widgets.stat_card import StatCard
from frontend.widgets.system_status import SystemStatus
from backend.services.lead_service import LeadService
from backend.services.group_service import GroupService


class DashboardPage(QWidget):

    def __init__(self, lead_service=None, group_service=None):
        super().__init__()
        self.setObjectName("dashboardPage")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.lead_service = lead_service or LeadService()
        self.group_service = group_service or GroupService()

        signals.facebook_login.connect(self.on_facebook_login)
        signals.facebook_status.connect(self.on_facebook_status)

        root = QVBoxLayout(self)
        root.setContentsMargins(25, 25, 25, 25)
        root.setSpacing(20)

        # ================= Title =================

        title = QLabel("Tổng quan")
        title.setObjectName("pageTitle")

        root.addWidget(title)
        description = QLabel("Theo dõi tài khoản, nhóm và các cơ hội bán hàng trong một không gian.")
        description.setObjectName("pageDescription")
        description.setWordWrap(True)
        root.addWidget(description)

        # ================= Stat Cards =================

        cards = self.cards_layout = QGridLayout()

        self.facebook_card = StatCard("Facebook", "Chưa kết nối")
        self.group_card = StatCard("Nhóm đã đồng bộ", "0")
        self.customer_card = StatCard("Khách hàng tiềm năng", "0")
        self.ai_card = StatCard("Bản nháp đã duyệt", "0")

        self.stat_cards = [self.facebook_card, self.group_card, self.customer_card, self.ai_card]
        for column, card in enumerate(self.stat_cards):
            cards.addWidget(card, 0, column)
        self._card_columns = 4

        root.addLayout(cards)

        # ================= Main Content =================

        bottom = self.bottom_layout = QBoxLayout(QBoxLayout.LeftToRight)

        left = QVBoxLayout()
        left.addWidget(ActivityWidget())

        bottom.addLayout(left, 2)

        right = QVBoxLayout()

        status_title = QLabel("Trạng thái hệ thống")
        status_title.setObjectName("sectionTitle")

        right.addWidget(SystemStatus())

        log_title = QLabel("Nhật ký hoạt động")
        log_title.setObjectName("sectionTitle")

        right.addWidget(log_title)
        right.addWidget(LogWidget(), 1)

        bottom.addLayout(right, 1)

        root.addLayout(bottom, 1)
        signals.leads_changed.connect(self.refresh_metrics, Qt.QueuedConnection)
        signals.groups_synced.connect(self.refresh_metrics, Qt.QueuedConnection)
        self.refresh_metrics()

    @Slot()
    @Slot(str, int)
    def refresh_metrics(self, *_args):
        try:
            summary = self.lead_service.summary()
            self.customer_card.set_value(str(summary["total"]))
            self.ai_card.set_value(str(summary["approved"]))
            self.group_card.set_value(str(len(self.group_service.get_all())))
        except Exception:
            self.customer_card.set_value("Chưa tải được")
            self.ai_card.set_value("Chưa tải được")

    def set_available_width(self, width):
        columns = 2 if width < 950 else 4
        if columns != self._card_columns:
            for card in self.stat_cards:
                self.cards_layout.removeWidget(card)
            for index, card in enumerate(self.stat_cards):
                self.cards_layout.addWidget(card, index // columns, index % columns)
            self._card_columns = columns
        self.bottom_layout.setDirection(
            QBoxLayout.TopToBottom if width < 950 else QBoxLayout.LeftToRight
        )

    # ================= Signals =================

    def on_facebook_login(self, account):

        self.facebook_card.set_value("Đã kết nối")

    def on_facebook_status(self, connected):
        self.facebook_card.set_value(
            "Đã kết nối" if connected else "Chưa kết nối"
        )
