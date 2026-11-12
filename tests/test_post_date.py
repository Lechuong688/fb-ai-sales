from datetime import datetime, timedelta
import unittest

from backend.facebook.parsers.post_date import VIETNAM_TZ, parse_post_date


class PostDateTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 1, 12, 0, tzinfo=VIETNAM_TZ)

    def test_exact_fifteen_day_boundary_and_future(self):
        for offset, expected in (
            (timedelta(days=15), "recent"),
            (timedelta(days=15, seconds=1), "old"),
            (timedelta(days=14, hours=23), "recent"),
            (timedelta(seconds=-1), "future"),
        ):
            with self.subTest(offset=offset):
                point = self.now - offset
                parsed = parse_post_date(str(int(point.timestamp())), self.now)
                self.assertEqual(parsed.classification(self.now), expected)

    def test_vietnamese_and_english_full_dates(self):
        for text in (
            "Thứ Ba, 20 tháng 10, 2026 lúc 14:35",
            "20 thg 10 2026 lúc 14:35", "20/10/2026 14:35",
            "October 20, 2026 at 2:35 PM", "20 October 2026 at 14:35",
            "2026-10-20T07:35:00Z", "2026-10-20T14:35:00+07:00",
        ):
            with self.subTest(text=text):
                parsed = parse_post_date(text, self.now)
                self.assertIsNotNone(parsed)
                self.assertEqual(parsed.oldest, datetime(2026, 10, 20, 14, 35, tzinfo=VIETNAM_TZ))
                self.assertEqual(parsed.classification(self.now), "recent")

    def test_relative_labels_are_conservative_intervals(self):
        for text, expected in (
            ("vừa xong", "recent"), ("5 phút", "recent"), ("2 giờ", "recent"),
            ("14 ngày", "recent"), ("15 ngày", "uncertain"), ("16 ngày", "old"),
            ("1 tuần", "recent"), ("2 tuần", "uncertain"), ("3 tuần", "old"),
            ("2 weeks ago", "uncertain"), ("1 tháng", "old"), ("3d", "recent"),
        ):
            with self.subTest(text=text):
                parsed = parse_post_date(text, self.now)
                self.assertIsNotNone(parsed)
                self.assertEqual(parsed.classification(self.now), expected)

    def test_today_yesterday_date_only_and_unknown(self):
        for text in ("Hôm qua lúc 15:20", "Yesterday at 3:20 PM"):
            self.assertEqual(parse_post_date(text, self.now).oldest,
                             datetime(2026, 10, 31, 15, 20, tzinfo=VIETNAM_TZ))
        self.assertEqual(parse_post_date("Hôm nay", self.now).classification(self.now), "recent")
        self.assertEqual(parse_post_date("17 tháng 10", self.now).classification(self.now), "uncertain")
        self.assertEqual(parse_post_date("18 tháng 10", self.now).classification(self.now), "recent")
        self.assertEqual(parse_post_date("01/10/2025", self.now).classification(self.now), "old")
        for text in ("", None, "Facebook", "Cần mua bếp từ", "31/02/2026", "arbitrary text"):
            with self.subTest(text=text):
                self.assertIsNone(parse_post_date(text, self.now))

    def test_year_rollover_and_milliseconds(self):
        now = datetime(2027, 1, 2, 12, tzinfo=VIETNAM_TZ)
        self.assertEqual(parse_post_date("31 tháng 12 lúc 10:00", now).oldest.year, 2026)
        self.assertEqual(parse_post_date(str(int(self.now.timestamp() * 1000)), self.now).oldest, self.now)


if __name__ == "__main__":
    unittest.main()
