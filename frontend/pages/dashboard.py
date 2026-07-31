from PySide6.QtWidgets import (
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from frontend.widgets.activity_widget import ActivityWidget
from frontend.widgets.log_widget import LogWidget
from frontend.widgets.stat_card import StatCard
from frontend.widgets.system_status import SystemStatus
from backend.services.dashboard_service import DashboardService


class DashboardPage(QWidget):

    def __init__(self):
        super().__init__()

        root = QVBoxLayout(self)

        root.setContentsMargins(25, 25, 25, 25)
        root.setSpacing(20)

        title = QLabel("Dashboard")
        title.setStyleSheet("""
            font-size:28px;
            font-weight:bold;
        """)

        root.addWidget(title)

        cards = QHBoxLayout()

        self.facebook_card = StatCard("Facebook", "Offline")
        self.group_card = StatCard("Groups", "0")
        self.customer_card = StatCard("Customers", "0")
        self.ai_card = StatCard("AI Score", "0%")

        cards.addWidget(self.facebook_card)
        cards.addWidget(self.group_card)
        cards.addWidget(self.customer_card)
        cards.addWidget(self.ai_card)
        cards.addWidget(StatCard("Customers", "38"))
        cards.addWidget(StatCard("AI Score", "98%"))

        root.addLayout(cards)

        bottom = QHBoxLayout()

        left = QVBoxLayout()

        left.addWidget(ActivityWidget())

        bottom.addLayout(left, 2)

        right = QVBoxLayout()

        right.addWidget(SystemStatus())
        right.addWidget(LogWidget())

        bottom.addLayout(right, 1)

        root.addLayout(bottom)
        log_title = QLabel("Application Log")
        log_title.setStyleSheet("""
            font-size:18px;
            font-weight:bold;
        """)

        root.addWidget(log_title)

        root.addWidget(LogWidget(), 1)
        DashboardService.register(self)
        # DashboardService.set_facebook_status("Online")
        # DashboardService.set_group_count(18)
        # DashboardService.set_customer_count(52)
        # DashboardService.set_ai_score("99%")