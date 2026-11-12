from datetime import datetime, timedelta
import json
import re
from urllib.parse import parse_qs, urlparse

from backend.database.repositories.lead_repository import LeadRepository
from backend.facebook.parsers.post_date import VIETNAM_TZ
from backend.services.comment_rules import post_identity, preview_comments
from backend.signals import signals


def real_post_url(value):
    parsed = urlparse(str(value or ""))
    host = (parsed.hostname or "").lower()
    if (parsed.scheme not in {"https", "http"} or parsed.username is not None
            or (host != "facebook.com" and not host.endswith(".facebook.com"))):
        return None
    query = parse_qs(parsed.query)
    valid = re.fullmatch(r"/(?:groups/[^/]+/)?(?:posts|permalink)/[^/]+/?", parsed.path)
    valid = valid or re.fullmatch(r"/[^/]+/posts/[^/]+/?", parsed.path)
    valid = valid or (parsed.path in {"/permalink.php", "/story.php"} and query.get("story_fbid") and query.get("id"))
    return post_identity(value) if valid else None


class LeadService:
    def __init__(self, repository=None, clock=None):
        self.repo = repository or LeadRepository()
        self.clock = clock or (lambda: datetime.now(VIETNAM_TZ))

    def _records(self, posts, rules=None, products=None, catalog=None):
        now = self.clock().astimezone(VIETNAM_TZ)
        records = {}
        for post in preview_comments(posts, rules, products, catalog):
            url = real_post_url(post.get("url"))
            if not url or post["status"] not in {"draft", "manual_review"}:
                continue
            try:
                oldest = datetime.fromisoformat(post["published_at"])
                newest = datetime.fromisoformat(post.get("published_until") or post["published_at"])
                if oldest.tzinfo is None or newest.tzinfo is None:
                    continue
                if not now - timedelta(days=15) <= oldest <= newest <= now:
                    continue
            except (KeyError, TypeError, ValueError):
                continue
            candidates = post.get("catalog_match", {}).get("candidates", [])
            records[url] = dict(
                post_url=url, author=str(post.get("author") or "Facebook user"), post_text=str(post.get("message") or ""),
                source_url=str(post.get("source_url") or ""), source_name=str(post.get("source_name") or ""),
                published_at=oldest.isoformat(), published_until=newest.isoformat(),
                product_label=post["product"], skus_json=json.dumps([item["sku"] for item in candidates], ensure_ascii=False),
                rule_name=post["rule_name"], rule_reason=post["reason"], requires_manual=post["status"] == "manual_review",
                suggested_comment=post["comment"],
            )
        return list(records.values())

    def capture_scan(self, profile, posts, rules=None, products=None, catalog=None):
        if not str(profile or "").strip() or profile in {"__samples__", "__company_samples__"}:
            raise ValueError("Cần profile thật đã đăng nhập để lưu kết quả quét.")
        records = self._records(posts, rules, products, catalog)
        result = self.repo.capture(profile.strip(), records)
        result["skipped"] = len(posts) - len(records)
        result["urls"] = [record["post_url"] for record in records]
        if result["saved"]:
            signals.leads_changed.emit()
        return result

    def save_drafts(self, profile, posts, rules=None, products=None, catalog=None):
        result = self.capture_scan(profile, posts, rules, products, catalog)
        drafts, errors = 0, []
        for post in posts:
            url = real_post_url(post.get("url"))
            if not url or url not in result["urls"]:
                continue
            current = self.repo.get_by_url(url)
            if not current:
                continue
            try:
                self.repo.save_review(
                    current["id"], current["version"], post.get("draft_comment", current["draft_comment"]),
                    current["notes"], current["workflow_status"], action="save",
                )
                drafts += 1
            except ValueError as exc:
                errors.append(str(exc))
        result.update(drafts=drafts, errors=errors)
        if drafts:
            signals.leads_changed.emit()
        return result

    def save_review(self, lead_id, version, comment, notes, status, action="save"):
        result = self.repo.save_review(lead_id, version, comment, notes, status, action)
        signals.leads_changed.emit()
        return result

    def list(self, **filters):
        return self.repo.list(**filters)

    def get(self, lead_id):
        return self.repo.get(lead_id)

    def summary(self):
        return self.repo.summary()
