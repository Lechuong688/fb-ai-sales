from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class AccountDialog(QDialog):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Thêm tài khoản")

        self.resize(420, 220)

        root = QVBoxLayout(self)

        form = QFormLayout()

        self.name = QLineEdit()
        self.uid = QLineEdit()
        self.profile = QLineEdit()

        form.addRow("Tên", self.name)
        form.addRow("UID", self.uid)
        form.addRow("Profile", self.profile)

        root.addLayout(form)

        buttons = QHBoxLayout()

        self.cancel = QPushButton("Huỷ")
        self.save = QPushButton("Lưu")

        buttons.addStretch()
        buttons.addWidget(self.cancel)
        buttons.addWidget(self.save)

        root.addLayout(buttons)

        self.cancel.clicked.connect(self.reject)
        self.save.clicked.connect(self.accept)

    def get_data(self):

        return {
            "name": self.name.text().strip(),
            "uid": self.uid.text().strip(),
            "profile": self.profile.text().strip()
        }