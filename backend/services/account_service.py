import re
import unicodedata

from backend.database.models.account import Account
from backend.database.repositories.account_repository import AccountRepository


class AccountService:

    def __init__(self):
        self.repo = AccountRepository()

    def get_all(self):
        accounts = self.repo.get_all()

        # Older login attempts could store the site URL in the UID column.
        # Facebook UIDs are numeric, so clear invalid legacy values instead
        # of continuing to display them as if the account were linked.
        for account in accounts:
            uid = (account.uid or "").strip()
            if uid and not uid.isdigit():
                account.uid = ""
                account.status = "Offline"
                self.repo.update(account)

        return accounts

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

        if uid and not uid.isdigit():
            raise ValueError("UID phải chỉ gồm chữ số.")

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

    def create_pending_facebook(self):
        """Create an empty account slot with a unique persistent browser profile."""
        used_profiles = {
            account.profile
            for account in self.repo.get_all()
            if account.profile
        }

        number = 1
        profile = f"Facebook{number}"
        while profile in used_profiles:
            number += 1
            profile = f"Facebook{number}"

        account = Account(
            name=f"Facebook {number}",
            uid="",
            profile=profile,
            status="Offline",
        )
        return self.repo.add(account)

    def update(self, account):

        uid = (account.uid or "").strip()
        if uid and not uid.isdigit():
            raise ValueError("UID phải chỉ gồm chữ số.")

        account.uid = uid

        self.repo.update(account)

    def delete(self, account_id):

        self.repo.delete(account_id)
