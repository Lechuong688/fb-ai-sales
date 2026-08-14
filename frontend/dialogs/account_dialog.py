from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLineEdit,
    QDialogButtonBox,
)


class AccountDialog(QDialog):

    def __init__(self, parent=None):

        super().__init__(parent)

        self.setWindowTitle(
            "Thêm tài khoản Facebook"
        )

        self.setMinimumWidth(420)

        layout = QFormLayout(self)

        self.name_input = QLineEdit()

        self.name_input.setPlaceholderText(
            "Ví dụ: Tổng Kho Bếp"
        )

        self.uid_input = QLineEdit()

        self.uid_input.setPlaceholderText(
            "Để trống - app tự lấy UID"
        )

        self.profile_input = QLineEdit()

        self.profile_input.setPlaceholderText(
            "Để trống - app tự tạo Profile"
        )

        layout.addRow(
            "Tên:",
            self.name_input
        )

        layout.addRow(
            "UID:",
            self.uid_input
        )

        layout.addRow(
            "Profile:",
            self.profile_input
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok |
            QDialogButtonBox.Cancel
        )

        buttons.accepted.connect(
            self.validate
        )

        buttons.rejected.connect(
            self.reject
        )

        layout.addRow(buttons)

    def validate(self):

        name = self.name_input.text().strip()

        if not name:

            self.name_input.setFocus()

            return

        self.accept()

    def get_data(self):

        return {
            "name": self.name_input.text().strip(),
            "uid": self.uid_input.text().strip(),
            "profile": self.profile_input.text().strip(),
        }