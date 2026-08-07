from PySide6.QtCore import QObject
from PySide6.QtCore import QTimer

from backend.browser.pool import browser_pool
from backend.services.account_service import AccountService
from backend.services.group_service import GroupService


class SessionService(QObject):

    def __init__(self):

        super().__init__()

        self.timer = QTimer()

        self.timer.timeout.connect(
            self.check_sessions
        )

    def start(self):

        self.timer.start(2000)

    # def check_sessions(self):

    #     sessions = browser_pool.get_all_sessions()

    #     for session in sessions:

    #         if not session.running:
    #             continue

    #         if session.synced:
    #             continue

    #         browser = browser_pool.get(
    #             session.profile
    #         )

    #         facebook = browser.facebook

    #         if not facebook.is_logged_in():
    #             continue

    #         profile = facebook.get_profile()

    #         account = AccountService().get_by_profile(
    #             session.profile
    #         )

    #         if account is None:
    #             continue

    #         account.uid = profile["uid"]
    #         account.name = profile["name"]
    #         account.status = "Online"

    #         AccountService().update(account)

    #         groups = facebook.get_groups()

    #         service = GroupService()

    #         for g in groups:

    #             service.create(
    #                 g["name"],
    #                 g["url"]
    #             )

    #         session.logged_in = True
    #         session.synced = True

    #         print(
    #             f"{profile['name']} synced."
    #         )

    def check_sessions(self):
        return