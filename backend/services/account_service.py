from backend.models.facebook_account import FacebookAccount


class AccountService:

    def __init__(self):

        self.accounts = []

    def load_demo(self):

        self.accounts = [

            FacebookAccount(
                1,
                "Kitchen Care",
                "100001",
                "Profile 1",
                "Online"
            ),

            FacebookAccount(
                2,
                "Bosch",
                "100002",
                "Profile 2",
                "Offline"
            ),

        ]

    def get_all(self):

        return self.accounts