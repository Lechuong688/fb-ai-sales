from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
)

from frontend.pages.base_page import BasePage


class GroupsPage(BasePage):

    def __init__(self):
        super().__init__(
            "Groups",
            "Quản lý các nhóm Facebook",
            "➕ Thêm nhóm"
        )

        groups = QListWidget()

        demo = [
            "Bosch Việt Nam",
            "Máy rửa bát",
            "Kitchen Care",
            "Bếp từ Chefs",
            "Teka Việt Nam"
        ]

        for item in demo:
            groups.addItem(QListWidgetItem(item))

        self.set_content(groups)