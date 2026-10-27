import requests
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QMessageBox
)

from frontend.widgets.page_header import PageHeader
from frontend.widgets.toolbar import Toolbar
from frontend.widgets.toolbar import Toolbar
from backend.facebook.comments import fetch_comments, post_comment


API_URL = "https://graph.facebook.com/v20.0"


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def fetch_comments(page_id: str, token: str, limit: int = 20) -> list[dict]:
    """Return a list of parsed comment dicts for a given Facebook page."""
    url = f"{API_URL}/{page_id}/feed"
    params = {"fields": "id,message,from,created_time", "limit": limit}
    resp = requests.get(url, headers=_auth_headers(token), params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    return [parse_comment(item) for item in data]


def post_comment(object_id: str, token: str, message: str) -> dict:
    """Post a comment to a post/comment identified by `object_id`."""
    url = f"{API_URL}/{object_id}/comments"
    payload = {"message": message}
    resp = requests.post(url, headers=_auth_headers(token), data=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def parse_comment(raw: dict) -> dict:
    """Extract a stable dict from the raw Graph API comment."""
    return {
        "id": raw.get("id"),
        "message": raw.get("message", ""),
        "author": raw.get("from", {}).get("name", "unknown"),
        "created_time": raw.get("created_time"),
    }


class BasePage(QWidget):

    def __init__(
        self,
        title: str,
        description: str = "",
        buttons=None
    ):
        super().__init__()

        self.layout = QVBoxLayout(self)

        self.layout.setContentsMargins(
            25,
            25,
            25,
            25
        )

        self.layout.setSpacing(20)

        self.header = PageHeader(
            title,
            description
        )

        self.toolbar = Toolbar(
            buttons=buttons
        )

        self.layout.addWidget(
            self.header
        )

        self.layout.addWidget(
            self.toolbar
        )

    def set_content(self, widget):

        self.layout.addWidget(widget)


