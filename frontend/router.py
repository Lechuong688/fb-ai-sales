from frontend.pages.dashboard import DashboardPage
from frontend.pages.accounts import AccountsPage
from frontend.pages.groups import GroupsPage


PAGES = [
    ("🏠 Dashboard", DashboardPage),
    ("👤 Accounts", AccountsPage),
    ("👥 Groups", GroupsPage),

    ("📰 Posts", None),
    ("💬 Customers", None),
    ("📨 Messenger", None),
    ("🤖 AI", None),
    ("📊 Reports", None),
    ("⚙ Settings", None),
]