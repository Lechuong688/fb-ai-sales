from backend.database.models.account import Account
from backend.database.repositories.account_repository import AccountRepository


class AccountService:

    def __init__(self):

        self.repo = AccountRepository()

    def get_all(self):

        return self.repo.get_all()

    def get(self, account_id):

        return self.repo.get(account_id)

    def create(
        self,
        name,
        uid,
        profile
    ):

        account = Account(
            name=name,
            uid=uid,
            profile=profile,
            status="Offline"
        )

        return self.repo.add(account)

    def update(self, account):

        return self.repo.update(account)

    def delete(self, account_id):

        self.repo.delete(account_id)

    def create_demo(self):

        if self.get_all():
            return

        self.create(
            "Kitchen Care",
            "100001",
            "KitchenCare"
        )

        self.create(
            "Bosch",
            "100002",
            "Bosch"
        )