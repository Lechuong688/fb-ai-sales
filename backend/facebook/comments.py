import requests
from .parsers.comment_parser import parse_comment

API_URL = "https://graph.facebook.com/v20.0"

def _auth_headers(token: str) -> dict:
    """Return the Authorization header for a given access token."""
    return {"Authorization": f"Bearer {token}"}

def fetch_comments(page_id: str, token: str, limit: int = 20) -> list[dict]:
    """Fetch recent comments/posts from a Facebook page.

    Args:
        page_id: Facebook page identifier.
        token: User access token with `pages_read_engagement` permission.
        limit: Number of items to retrieve (default 20).
    Returns:
        A list of dictionaries with keys ``id``, ``message``, ``author`` and ``created_time``.
    """
    url = f"{API_URL}/{page_id}/feed"
    params = {"fields": "id,message,from,created_time", "limit": limit}
    resp = requests.get(url, headers=_auth_headers(token), params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    return [parse_comment(item) for item in data]

def post_comment(object_id: str, token: str, message: str) -> dict:
    """Post a comment to a Facebook post or comment.

    Args:
        object_id: The ``id`` of the post or comment to reply to.
        token: Access token with ``pages_manage_posts`` permission.
        message: Text of the comment.
    Returns:
        The JSON response from the Graph API.
    """
    url = f"{API_URL}/{object_id}/comments"
    payload = {"message": message}
    resp = requests.post(url, headers=_auth_headers(token), data=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()
