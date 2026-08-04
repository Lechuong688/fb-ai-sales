from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
)

from frontend.widgets.page_header import PageHeader
from frontend.widgets.toolbar import Toolbar


class BasePage(QWidget):

    def __init__(
        self,
        title: str,
        description: str,
        buttons=None,
    ):
        super().__init__()

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(25, 25, 25, 25)
        self.layout.setSpacing(20)

        # Header
        self.header = PageHeader(
            title,
            description
        )

        self.layout.addWidget(self.header)

        # Toolbar
        self.toolbar = Toolbar(
            buttons=buttons
        )

        self.layout.addWidget(self.toolbar)

    def set_content(self, widget):

        self.layout.addWidget(widget)