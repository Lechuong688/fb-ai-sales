import re
import unicodedata

from backend.database.models.account import Account
from backend.database.repositories.account_repository import AccountRepository


class AccountService:

    def __init__(self):
        self.repo = AccountRepository()

    def get_all(self):
        return self.repo.get_all()

    def get(self, account_id):
        return self.repo.get(account_id)

    def get_by_profile(self, profile):
        accounts = self.repo.get_all()

        for account in accounts:
            if account.profile == profile:
                return account

        return None

    def _generate_profile(self, name):

        text = unicodedata.normalize(
            "NFD",
            name
        )

        text = "".join(
            char
            for char in text
            if unicodedata.category(char) != "Mn"
        )

        text = re.sub(
            r"[^a-zA-Z0-9]+",
            "",
            text
        )

        if not text:
            text = "Facebook"

        base = text
        profile = base
        number = 1

        while self.get_by_profile(profile):

            number += 1
            profile = f"{base}{number}"

        return profile

    def create(self, name, uid="", profile=""):

        name = name.strip()
        uid = uid.strip()
        profile = profile.strip()

        if not name:
            raise ValueError(
                "Tên tài khoản không được để trống."
            )

        # Không nhập Profile -> tự tạo
        if not profile:
            profile = self._generate_profile(name)

        account = Account(
            name=name,
            uid=uid,
            profile=profile,
            status="Offline"
        )

        return self.repo.add(account)

    def update(self, account):

        self.repo.update(account)

    def delete(self, account_id):

        self.repo.delete(account_id)