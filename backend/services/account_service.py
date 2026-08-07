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

    def create(self, name, uid, profile):

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