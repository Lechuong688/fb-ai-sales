from PySide6.QtWidgets import (
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from backend.signals import signals
from frontend.widgets.activity_widget import ActivityWidget
from frontend.widgets.log_widget import LogWidget
from frontend.widgets.stat_card import StatCard
from frontend.widgets.system_status import SystemStatus


class DashboardPage(QWidget):

    def __init__(self):
        super().__init__()

        signals.facebook_login.connect(self.on_facebook_login)

        root = QVBoxLayout(self)
        root.setContentsMargins(25, 25, 25, 25)
        root.setSpacing(20)

        # ================= Title =================

        title = QLabel("Dashboard")
        title.setStyleSheet("""
            font-size:28px;
            font-weight:bold;
        """)

        root.addWidget(title)

        # ================= Stat Cards =================

        cards = QHBoxLayout()

        self.facebook_card = StatCard("Facebook", "🔴 Offline")
        self.group_card = StatCard("Groups", "0")
        self.customer_card = StatCard("Customers", "0")
        self.ai_card = StatCard("AI Score", "0%")

        cards.addWidget(self.facebook_card)
        cards.addWidget(self.group_card)
        cards.addWidget(self.customer_card)
        cards.addWidget(self.ai_card)

        root.addLayout(cards)

        # ================= Main Content =================

        bottom = QHBoxLayout()

        left = QVBoxLayout()
        left.addWidget(ActivityWidget())

        bottom.addLayout(left, 2)

        right = QVBoxLayout()

        status_title = QLabel("System Status")
        status_title.setStyleSheet("""
            font-size:18px;
            font-weight:bold;
        """)

        right.addWidget(status_title)
        right.addWidget(SystemStatus())

        log_title = QLabel("Application Log")
        log_title.setStyleSheet("""
            font-size:18px;
            font-weight:bold;
        """)

        right.addWidget(log_title)
        right.addWidget(LogWidget(), 1)

        bottom.addLayout(right, 1)

        root.addLayout(bottom)

    # ================= Signals =================

    def on_facebook_login(self, account):

        self.facebook_card.set_value("🟢 Online")