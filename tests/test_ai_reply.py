import json
import unittest
from unittest.mock import patch

from backend.ai.reply import _extract_output_text, _parse_suggestions, suggest_replies


class AIReplyTests(unittest.TestCase):
    def test_extracts_text_from_all_message_output_items(self):
        response = {
            "output": [
                {"type": "reasoning", "summary": []},
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "Gợi ý một"},
                        {"type": "refusal", "refusal": ""},
                    ],
                },
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "Gợi ý hai"}],
                },
            ]
        }
        self.assertEqual(_extract_output_text(response), "Gợi ý một\nGợi ý hai")

    def test_parses_bulleted_suggestions_and_limits_to_three(self):
        text = "- Dòng một\n• Dòng hai\n3. Dòng ba\n4. Bỏ qua"
        self.assertEqual(
            _parse_suggestions(text), ["Dòng một", "Dòng hai", "Dòng ba"]
        )

    def test_suggest_replies_sends_responses_request(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps(
                    {
                        "output": [
                            {
                                "type": "message",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": "Bạn cho mình xin thêm thông tin nhé?\nShop có thể tư vấn thêm ạ.\nBạn cần mẫu nào ạ?",
                                    }
                                ],
                            }
                        ]
                    }
                ).encode("utf-8")

        with patch("backend.ai.reply.get_openai_settings", return_value=("test-key", "test-model")):
            with patch("backend.ai.reply.urlopen", return_value=FakeResponse()) as open_url:
                result = suggest_replies("Mọi người biết chỗ nào bán bàn không?")

        self.assertEqual(len(result), 3)
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(json.loads(request.data)["model"], "test-model")


if __name__ == "__main__":
    unittest.main()
