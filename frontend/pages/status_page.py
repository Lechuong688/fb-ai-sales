from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from frontend.pages.base_page import BasePage
import os

import os
from backend.services.account_service import AccountService

class StatusPage(BasePage):
    """Page that shows a live web view with the status of all logged‑in Facebook accounts.
    The HTML file is generated in the same folder (status.html) and can be refreshed
    manually or via JavaScript. For a production app you would serve a local HTTP
    endpoint that returns JSON with account states, but a static file is enough for
    the demo.
    """

    def __init__(self):
        super().__init__(
            title="Live Status",
            description="Xem trạng thái các nick đang chạy",
            buttons=None,
        )

        # Create the web view widget
        self.web_view = QWebEngineView()
        # Resolve the absolute path to the HTML file
        html_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "status.html"))
        self.web_view.setUrl(QUrl.fromLocalFile(html_path))
        self.layout.addWidget(self.web_view)
