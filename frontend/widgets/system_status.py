from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class SystemStatus(QFrame):

    def __init__(self):
        super().__init__()

        self.setObjectName("card")

        layout = QVBoxLayout(self)

        title = QLabel("System Status")
        title.setObjectName("cardTitle")

        layout.addWidget(title)

        layout.addWidget(QLabel("🟢 Facebook : Connected"))
        layout.addWidget(QLabel("🟢 Browser : Ready"))
        layout.addWidget(QLabel("🟡 AI : Idle"))
        layout.addWidget(QLabel("⚪ Database : Waiting"))

        layout.addStretch()