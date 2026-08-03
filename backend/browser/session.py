from dataclasses import dataclass
from datetime import datetime

from playwright.sync_api import BrowserContext
from playwright.sync_api import Page


@dataclass
class BrowserSession:

    profile: str

    context: BrowserContext | None = None

    page: Page | None = None

    logged_in: bool = False

    running: bool = False

    started_at: datetime | None = None

    last_active: datetime | None = None