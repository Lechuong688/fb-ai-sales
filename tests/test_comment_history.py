import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.repositories.comment_history_repository import (
    CommentHistoryRepository,
)


class CommentHistoryTests(unittest.TestCase):
    def test_successful_comment_is_deduplicated_per_profile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = create_engine(f"sqlite:///{Path(temp_dir) / 'test.db'}")
            repository = CommentHistoryRepository(
                db_engine=engine,
                session_factory=sessionmaker(bind=engine),
            )

            self.assertFalse(repository.was_sent("profile-a", "https://fb/p/1"))
            repository.record("profile-a", "https://fb/p/1", "Hello", "sent")

            self.assertTrue(repository.was_sent("profile-a", "https://fb/p/1"))
            self.assertFalse(repository.was_sent("profile-b", "https://fb/p/1"))

            recent = repository.get_recent()
            self.assertEqual(len(recent), 1)
            self.assertEqual(recent[0]["status"], "sent")
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
