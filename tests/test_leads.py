from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest
import json
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.database.repositories.lead_repository import LeadRepository, LeadConflict
from backend.facebook.parsers.post_date import VIETNAM_TZ
from backend.services.lead_service import LeadService, real_post_url


NOW = datetime(2026, 11, 3, 12, tzinfo=VIETNAM_TZ)


def buyer_post(number=1, text="Mình cần mua bếp từ cho gia đình"):
    return dict(
        url=f"https://www.facebook.com/groups/100/posts/{number}/?ref=share",
        author="Khách hàng A", message=text, source_url="https://www.facebook.com/groups/100/",
        source_name="Hội nội thất", published_at=(NOW - timedelta(days=1)).isoformat(),
        published_until=(NOW - timedelta(days=1)).isoformat(),
    )


class LeadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.directory.name)/'leads.db'}")
        self.factory = sessionmaker(bind=self.engine, autoflush=False)
        self.repo = LeadRepository(self.engine, self.factory)
        self.service = LeadService(self.repo, clock=lambda: NOW)

    def tearDown(self):
        self.engine.dispose()
        self.directory.cleanup()

    def first(self):
        return self.service.list()["records"][0]

    def test_capture_persists_and_can_reopen_with_another_service(self):
        result = self.service.capture_scan("nick-a", [buyer_post()])
        self.assertEqual(result["created"], 1)
        reopened = LeadService(LeadRepository(self.engine, self.factory), clock=lambda: NOW)
        lead = reopened.list()["records"][0]
        self.assertEqual(lead["author"], "Khách hàng A")
        self.assertEqual(lead["workflow_status"], "new")
        self.assertEqual(lead["review_status"], "pending")
        self.assertEqual(lead["profiles"], ["nick-a"])
        self.assertTrue(lead["draft_comment"])
        self.assertNotIn("ref=", lead["post_url"])

    def test_repeated_scans_and_different_accounts_keep_one_lead(self):
        self.service.capture_scan("nick-a", [buyer_post()])
        first_seen = self.first()["first_seen"]
        mobile = dict(buyer_post(), url="https://m.facebook.com/groups/100/posts/1/#comments")
        self.service.capture_scan("nick-b", [mobile, buyer_post()])
        self.assertEqual(self.service.summary()["total"], 1)
        lead = self.first()
        self.assertEqual(lead["profiles"], ["nick-a", "nick-b"])
        self.assertEqual(lead["first_seen"], first_seen)

    def test_manual_reply_notes_and_workflow_survive_rescan(self):
        self.service.capture_scan("nick-a", [buyer_post()])
        lead = self.first()
        self.service.save_review(lead["id"], lead["version"], "Bản nháp mình đã sửa", "Gọi lại chiều mai", "follow_up", "approve")
        self.service.capture_scan("nick-b", [buyer_post()])
        saved = self.first()
        self.assertEqual(saved["draft_comment"], "Bản nháp mình đã sửa")
        self.assertEqual(saved["draft_origin"], "manual")
        self.assertEqual(saved["notes"], "Gọi lại chiều mai")
        self.assertEqual(saved["workflow_status"], "follow_up")
        self.assertEqual(saved["review_status"], "approved")

    def test_context_change_invalidates_approval_without_overwriting_manual_text(self):
        self.service.capture_scan("nick-a", [buyer_post()])
        lead = self.first()
        self.service.save_review(lead["id"], lead["version"], "Bản nháp riêng", "Khách cần gọi lại", "contacting", "approve")
        self.service.capture_scan("nick-a", [buyer_post(text="Mình cần mua bếp từ ngân sách dưới 5 triệu")])
        saved = self.first()
        self.assertEqual(saved["review_status"], "pending")
        self.assertEqual(saved["draft_comment"], "Bản nháp riêng")
        self.assertEqual(saved["notes"], "Khách cần gọi lại")
        self.assertIn("ngân sách", saved["suggested_comment"])

    def test_editing_approved_draft_requires_reapproval_but_notes_only_do_not(self):
        self.service.capture_scan("nick-a", [buyer_post()])
        lead = self.first()
        approved = self.service.save_review(lead["id"], lead["version"], lead["draft_comment"], "", "new", "approve")
        notes = self.service.save_review(approved["id"], approved["version"], approved["draft_comment"], "Ghi chú mới", "new")
        self.assertEqual(notes["review_status"], "approved")
        edited = self.service.save_review(notes["id"], notes["version"], "Nội dung khác", notes["notes"], "new")
        self.assertEqual(edited["review_status"], "pending")

    def test_samples_undated_old_future_and_seller_posts_are_not_saved(self):
        old = dict(buyer_post(2), published_at=(NOW - timedelta(days=16)).isoformat(), published_until=(NOW-timedelta(days=16)).isoformat())
        future = dict(buyer_post(3), published_at=(NOW + timedelta(days=1)).isoformat(), published_until=(NOW+timedelta(days=1)).isoformat())
        undated = buyer_post(4)
        undated.pop("published_at")
        sample = dict(buyer_post(5), url="sample://offline/5")
        seller = buyer_post(6, "Bên em bán bếp từ, ai cần mua inbox")
        result = self.service.capture_scan("nick-a", [buyer_post(), old, future, undated, sample, seller])
        self.assertEqual(result["saved"], 1)
        self.assertEqual(result["skipped"], 5)
        self.assertEqual(self.service.summary()["total"], 1)

    def test_search_without_accents_filters_and_pagination(self):
        self.service.capture_scan("nick-a", [buyer_post(number) for number in range(1, 4)])
        lead = self.first()
        self.service.save_review(lead["id"], lead["version"], lead["draft_comment"], "Cần gọi lại khách Hà Nội", "follow_up")
        result = self.service.list(query="goi lai khach ha noi", status="follow_up", review="pending")
        self.assertEqual(result["total"], 1)
        self.assertEqual(self.service.list(query="khach hang a")["total"], 3)
        first_page = self.service.list(limit=2)
        second_page = self.service.list(offset=2, limit=2)
        self.assertEqual(first_page["total"], 3)
        self.assertEqual(len(first_page["records"]), 2)
        self.assertEqual(len(second_page["records"]), 1)
        self.assertEqual(self.service.summary()["follow_up"], 1)

    def test_stale_version_cannot_overwrite_newer_changes(self):
        self.service.capture_scan("nick-a", [buyer_post()])
        original = self.first()
        self.service.save_review(original["id"], original["version"], "Bản mới", "Ghi chú mới", "contacting")
        with self.assertRaises(LeadConflict):
            self.service.save_review(original["id"], original["version"], "Bản cũ", "", "new")
        self.assertEqual(self.first()["draft_comment"], "Bản mới")
        self.assertEqual(self.first()["notes"], "Ghi chú mới")

    def test_compact_model_code_search(self):
        record = self.service._records([buyer_post()])[0]
        record["skus_json"] = json.dumps(["EU-T685MAX"])
        self.repo.capture("nick-a", [record])
        self.assertEqual(self.service.list(query="eut685max")["total"], 1)
        self.assertEqual(self.service.list(query="EU-T685MAX")["total"], 1)

    def test_failed_capture_rolls_back_the_whole_batch(self):
        self.service.capture_scan("nick-a", [buyer_post()])
        record = self.service._records([buyer_post(2)])[0]
        with self.assertRaises(IntegrityError):
            self.repo.capture("nick-a", [record, record])
        self.assertEqual(self.service.summary()["total"], 1)

    def test_selected_drafts_are_saved_locally_and_invalid_ones_are_excluded(self):
        with patch("backend.services.lead_service.signals") as events:
            result = self.service.save_drafts("nick-a", [dict(buyer_post(), draft_comment="Bản đã sửa ở Comment"), dict(buyer_post(2), url="sample://demo")])
        self.assertEqual(result["drafts"], 1)
        self.assertEqual(self.first()["draft_comment"], "Bản đã sửa ở Comment")
        self.assertEqual(self.first()["draft_origin"], "manual")
        self.assertEqual(self.first()["review_status"], "pending")
        self.assertTrue(events.leads_changed.emit.called)

    def test_invalid_review_and_empty_approval_are_rejected(self):
        self.service.capture_scan("nick-a", [buyer_post()])
        lead = self.first()
        for comment, status, action in (("", "new", "approve"), ("text", "invalid", "save"), ("text", "new", "send")):
            with self.subTest(action=action), self.assertRaises(ValueError):
                self.service.save_review(lead["id"], lead["version"], comment, "", status, action)
        self.assertEqual(self.first()["review_status"], "pending")

    def test_rejected_draft_and_ignored_workflow_survive_repeated_scan(self):
        self.service.capture_scan("nick-a", [buyer_post()])
        lead = self.first()
        self.service.save_review(lead["id"], lead["version"], lead["draft_comment"], "Không phù hợp", "ignored", "reject")
        self.service.capture_scan("nick-b", [buyer_post()])
        self.assertEqual(self.first()["review_status"], "rejected")
        self.assertEqual(self.first()["workflow_status"], "ignored")

    def test_only_real_facebook_post_links_are_accepted(self):
        for value in ("sample://case/1", "https://evil.test/groups/1/posts/2/", "https://facebook.com/groups/1/", "https://user@facebook.com/posts/1/"):
            self.assertIsNone(real_post_url(value))
        self.assertTrue(real_post_url("https://m.facebook.com/groups/1/posts/2?ref=share"))


if __name__ == "__main__":
    unittest.main()
