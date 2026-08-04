from PySide6.QtWidgets import QLabel


class Breadcrumb(QLabel):

    def __init__(self):
        super().__init__()

        self.setObjectName("breadcrumb")

        self.set_page("Dashboard")

    def set_page(self, page):

        self.setText(f"🏠 {page}")