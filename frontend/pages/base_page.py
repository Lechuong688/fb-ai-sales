from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
)

from frontend.widgets.page_header import PageHeader
from frontend.widgets.toolbar import PageToolbar


class BasePage(QWidget):

    def __init__(
        self,
        title: str,
        description: str,
        add_button_text="Thêm"
    ):
        super().__init__()

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(25, 25, 25, 25)
        self.layout.setSpacing(20)

        self.header = PageHeader(title, description)
        self.toolbar = PageToolbar(add_button_text)

        self.layout.addWidget(self.header)
        self.layout.addWidget(self.toolbar)

    def set_content(self, widget):
        self.layout.addWidget(widget)