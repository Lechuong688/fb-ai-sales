import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.browser.facebook import FacebookBrowser
from backend.services.comment_rules import (
    CommentRuleStore, DEFAULT_RULES, contains_phrase, post_identity,
    preview_comments, suggest_comment, validate_rules,
)
from backend.services.comment_samples import SAMPLE_CASES, sample_posts
from backend.workers.browser_worker import BrowserWorker


class CommentRuleTests(unittest.TestCase):
    def test_realistic_scenarios(self):
        for text, expected in SAMPLE_CASES:
            with self.subTest(text=text):
                result = suggest_comment(text)
                self.assertEqual(result["rule_id"] or None, expected)
                self.assertEqual(bool(result["comment"]), expected is not None)
                if expected:
                    self.assertIn(result["status"], {"draft", "manual_review"})
                    self.assertNotIn("{san_pham}", result["comment"])
                    self.assertTrue(result["matched_keywords"])
                else:
                    self.assertEqual(result["status"], "skipped")

    def test_user_example_uses_availability_reply(self):
        result = suggest_comment("có bác nào có bếp từ này không")
        self.assertEqual(result["rule_id"], "availability")
        self.assertIn("Bên em có ạ", result["comment"])
        self.assertIn("báo giá", result["comment"])

    def test_repairs_installation_and_accessories_need_manual_review(self):
        for text in ("Bếp từ báo lỗi E0", "Cần lắp máy hút mùi", "Cần mua nồi cho bếp từ"):
            with self.subTest(text=text):
                self.assertEqual(suggest_comment(text)["status"], "manual_review")

    def test_normalization_handles_accents_case_punctuation_and_boundaries(self):
        self.assertTrue(contains_phrase("CÓ BÁC NÀO CÓ\nbếp-từ này?", "co bac nao co"))
        self.assertFalse(contains_phrase("Toshiba", "ib"))
        self.assertFalse(contains_phrase("không cần mua", "cần mu"))
        self.assertTrue(FacebookBrowser.matches_buying_intent("CO BAC NAO CO BEP TU NAY KHONG", ["có bác nào có"]))

    def test_custom_rule_precedes_default_and_substitutes_product(self):
        custom = dict(id="test", name="Khách hỏi mã X", keywords=["mã x123"],
                      reply="Bác ib em mã {san_pham} X123 nhé.", manual=False)
        result = suggest_comment("Ai có bếp từ mã X123 không?", [custom] + copy.deepcopy(DEFAULT_RULES))
        self.assertEqual(result["rule_id"], "test")
        self.assertEqual(result["comment"], "Bác ib em mã bếp từ X123 nhé.")

    def test_empty_product_list_never_matches(self):
        self.assertEqual(suggest_comment("Ai bán bếp từ?", products=[])["status"], "skipped")

    def test_rule_validation_rejects_bad_templates_and_empty_keywords(self):
        for template in ("{unknown}", "{san_pham.__class__}", "{san_pham!r}", "{san_pham:100000000}", "{"):
            rules = copy.deepcopy(DEFAULT_RULES)
            rules[0]["reply"] = template
            with self.subTest(template=template), self.assertRaises(ValueError):
                validate_rules(rules)
        rules = copy.deepcopy(DEFAULT_RULES)
        rules[0]["keywords"] = []
        with self.assertRaises(ValueError):
            validate_rules(rules)
        with self.assertRaises(ValueError):
            validate_rules([])

    def test_tracking_variants_are_deduplicated_without_losing_post_ids(self):
        posts = [
            dict(message="Cần mua bếp từ", url="https://www.facebook.com/groups/1/posts/2/?ref=share"),
            dict(message="Cần mua bếp từ", url="https://m.facebook.com/groups/1/posts/2/#comments"),
            dict(message="Cần mua bếp từ", url="https://www.facebook.com/groups/1/posts/3/"),
        ]
        result = preview_comments(posts)
        self.assertEqual([item["status"] for item in result], ["draft", "duplicate", "draft"])
        self.assertEqual(result[1]["comment"], "")
        self.assertNotEqual(post_identity("https://facebook.com/permalink.php?story_fbid=1&id=3"),
                            post_identity("https://facebook.com/permalink.php?story_fbid=2&id=3"))

    def test_rule_store_persists_edits_and_rejects_corrupt_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CommentRuleStore(Path(directory) / "rules.json")
            rules = store.load()
            rules[0]["reply"] = "Bản nháp cho {san_pham}."
            store.save(rules)
            self.assertEqual(store.load()[0]["reply"], rules[0]["reply"])
            self.assertNotEqual(DEFAULT_RULES[0]["reply"], rules[0]["reply"])
            store.path.write_text(json.dumps({"not": "rules"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                store.load()

    def test_worker_cannot_send_even_when_request_asks_for_live_mode(self):
        worker = BrowserWorker()
        worker.profile_name = "test-only"
        with patch("backend.workers.browser_worker.browser_pool") as pool, \
             patch("backend.workers.browser_worker.CommentHistoryService") as history, \
             patch("backend.workers.browser_worker.signals") as events:
            pool.get.side_effect = AssertionError("Must not access a live browser")
            history.side_effect = AssertionError("Must not write sent history")
            worker.comment_on_posts({"posts": sample_posts(), "dry_run": False, "approved_for_live": True})
            pool.get.assert_not_called()
            history.assert_not_called()
            self.assertEqual(events.comment_result.emit.call_count, len(SAMPLE_CASES))
            for call in events.comment_result.emit.call_args_list:
                self.assertTrue(call.args[1]["dry_run"])
                self.assertFalse(call.args[1]["success"])


if __name__ == "__main__":
    unittest.main()
