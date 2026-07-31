from PySide6.QtWidgets import (
    QLabel,
    QWidget,
    QVBoxLayout,
)


class LoadingWidget(QWidget):

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)

        label = QLabel("Loading...")

        layout.addStretch()
        layout.addWidget(label)
        layout.addStretch()

        self.hide()