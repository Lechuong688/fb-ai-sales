from PySide6.QtWidgets import QLabel


class Breadcrumb(QLabel):

    def __init__(self):
        super().__init__()

        self.setText("Dashboard")

    def set_page(self, page):

        self.setText(page)