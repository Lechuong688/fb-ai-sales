def parse_comment(raw: dict) -> dict:
    """Extract a stable dict from the raw Graph API comment.

    Parameters
    ----------
    raw: dict
        Raw JSON object returned by the Facebook Graph API.

    Returns
    -------
    dict
        Dictionary with keys ``id``, ``message``, ``author`` and ``created_time``.
    """
    return {
        "id": raw.get("id"),
        "message": raw.get("message", ""),
        "author": raw.get("from", {}).get("name", "unknown"),
        "created_time": raw.get("created_time"),
    }
