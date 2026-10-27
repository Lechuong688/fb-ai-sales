import json

from backend.database.repositories.post_draft_repository import PostDraftRepository


class PostDraftService:
    def __init__(self):
        self.repo = PostDraftRepository()

    def get_all(self):
        return self.repo.get_all()

    def save(self, draft_id, content, media_paths, target_profiles, target_groups):
        return self.repo.save(
            draft_id=draft_id,
            content=(content or "").strip(),
            media_paths=media_paths,
            target_profiles=target_profiles,
            target_groups=target_groups,
        )

    def delete(self, draft_id):
        self.repo.delete(draft_id)

    @staticmethod
    def decode_list(value):
        try:
            result = json.loads(value or "[]")
            return result if isinstance(result, list) else []
        except (TypeError, json.JSONDecodeError):
            return []

    @staticmethod
    def decode_groups(value):
        try:
            result = json.loads(value or "{}")
            return result if isinstance(result, dict) else {}
        except (TypeError, json.JSONDecodeError):
            return {}
