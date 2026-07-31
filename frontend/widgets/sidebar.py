from PySide6.QtWidgets import QListWidget, QListWidgetItem


class Sidebar(QListWidget):
    def __init__(self):
        super().__init__()

        self.setFixedWidth(220)

        menus = [
            "🏠 Dashboard",
            "👤 Accounts",
            "👥 Groups",
            "📰 Posts",
            "💬 Customers",
            "🤖 AI",
            "📊 Reports",
            "⚙ Settings",
        ]

        for menu in menus:
            self.addItem(QListWidgetItem(menu))