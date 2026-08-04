from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)


class LoadingWidget(QWidget):

    def __init__(self):
        super().__init__()

        self.setObjectName("loadingOverlay")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(15)

        self.title = QLabel("Loading...")
        self.title.setObjectName("loadingTitle")
        self.title.setAlignment(Qt.AlignCenter)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)      # Infinite progress
        self.progress.setFixedWidth(220)
        self.progress.setTextVisible(False)

        self.message = QLabel("Please wait")
        self.message.setObjectName("loadingMessage")
        self.message.setAlignment(Qt.AlignCenter)

        layout.addStretch()
        layout.addWidget(self.title)
        layout.addWidget(self.progress)
        layout.addWidget(self.message)
        layout.addStretch()

        self.hide()

    def show_loading(self, message="Loading..."):
        self.title.setText(message)
        self.show()
        self.raise_()

    def hide_loading(self):
        self.hide()