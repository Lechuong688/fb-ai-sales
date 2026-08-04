from PySide6.QtWidgets import (
    QLabel,
    QFrame,
    QVBoxLayout,
)

from backend.signals import signals


class SystemStatus(QFrame):

    def __init__(self):
        super().__init__()

        self.setObjectName("card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel("System Status")
        title.setObjectName("cardTitle")

        layout.addWidget(title)

        self.facebook = QLabel()
        self.browser = QLabel()
        self.ai = QLabel()
        self.database = QLabel()

        layout.addWidget(self.facebook)
        layout.addWidget(self.browser)
        layout.addWidget(self.ai)
        layout.addWidget(self.database)

        layout.addStretch()

        self.set_facebook(False)
        self.set_browser(False)
        self.set_ai("Idle")
        self.set_database(False)

        # Nếu sau này có signal thì chỉ cần emit là UI tự cập nhật
        if hasattr(signals, "facebook_status"):
            signals.facebook_status.connect(self.set_facebook)

        if hasattr(signals, "browser_status"):
            signals.browser_status.connect(self.set_browser)

        if hasattr(signals, "database_status"):
            signals.database_status.connect(self.set_database)

    # -----------------------------
    # Facebook
    # -----------------------------

    def set_facebook(self, connected: bool):

        if connected:
            self.facebook.setText("🟢 Facebook     Connected")
        else:
            self.facebook.setText("🔴 Facebook     Offline")

    # -----------------------------
    # Browser
    # -----------------------------

    def set_browser(self, ready: bool):

        if ready:
            self.browser.setText("🟢 Browser      Ready")
        else:
            self.browser.setText("🔴 Browser      Closed")

    # -----------------------------
    # AI
    # -----------------------------

    def set_ai(self, status: str):

        self.ai.setText(f"🤖 AI               {status}")

    # -----------------------------
    # Database
    # -----------------------------

    def set_database(self, connected: bool):

        if connected:
            self.database.setText("🟢 Database    Connected")
        else:
            self.database.setText("🟡 Database    Waiting")