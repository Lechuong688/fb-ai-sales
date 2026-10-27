from backend.database.repositories.comment_history_repository import (
    CommentHistoryRepository,
)


class CommentHistoryService:
    def __init__(self):
        self.repo = CommentHistoryRepository()

    def was_sent(self, account_profile, post_url):
        return self.repo.was_sent(account_profile, post_url)

    def record(self, account_profile, post_url, comment_text, status, error=""):
        self.repo.record(account_profile, post_url, comment_text, status, error)

    def get_recent(self, limit=12):
        return self.repo.get_recent(limit)
