"""Shared validation for group links collected from Facebook or entered by users."""

import re
from urllib.parse import quote, unquote, urljoin, urlparse


RESERVED_GROUP_PATHS = {
    "feed", "joins", "discover", "search", "create", "notifications",
    "categories", "category", "invites", "pending", "your_groups", "admin",
}


def normalize_group_url(value):
    """Return one canonical group URL, or raise for navigation/post/external URLs."""
    parsed = urlparse(urljoin("https://www.facebook.com/", str(value or "").strip()))
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme not in {"http", "https"}
        or (host != "facebook.com" and not host.endswith(".facebook.com"))
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 80, 443}
    ):
        raise ValueError("URL nhóm phải thuộc Facebook.")
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) != 2 or parts[0].lower() != "groups":
        raise ValueError("Hãy dùng URL trang nhóm Facebook, không dùng link bài viết.")
    group_id = parts[1]
    if (
        group_id.casefold() in RESERVED_GROUP_PATHS
        or group_id in {".", ".."}
        or not re.fullmatch(r"[\w.-]+", group_id)
    ):
        raise ValueError("URL không chứa mã hoặc tên nhóm Facebook hợp lệ.")
    return f"https://www.facebook.com/groups/{quote(group_id, safe='._-')}/"
