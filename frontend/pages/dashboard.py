from PySide6.QtWidgets import (
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from frontend.widgets.activity_widget import ActivityWidget
from frontend.widgets.stat_card import StatCard


class DashboardPage(QWidget):

    def __init__(self):
        super().__init__()

        root = QVBoxLayout(self)
        root.setContentsMargins(25, 25, 25, 25)
        root.setSpacing(20)

        title = QLabel("Dashboard")
        title.setStyleSheet("font-size:28px;font-weight:bold;")

        root.addWidget(title)

        cards = QHBoxLayout()
        cards.setSpacing(15)

        cards.addWidget(StatCard("Facebook", "Online"))
        cards.addWidget(StatCard("Groups", "15"))
        cards.addWidget(StatCard("Customers", "38"))
        cards.addWidget(StatCard("AI Score", "98%"))

        root.addLayout(cards)

        root.addWidget(ActivityWidget(), 1)