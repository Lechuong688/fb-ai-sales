"""Conservative Facebook post-date parsing in the user's Vietnam timezone."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re

from backend.utils.text_matching import normalize_text


VIETNAM_TZ = timezone(timedelta(hours=7))


@dataclass(frozen=True)
class PostDate:
    oldest: datetime
    newest: datetime
    precision: str

    def classification(self, now, days=15):
        cutoff = now - timedelta(days=days)
        if self.newest < cutoff:
            return "old"
        if self.oldest > now:
            return "future"
        if self.oldest >= cutoff and self.newest <= now:
            return "recent"
        return "uncertain"


def parse_post_date(value, now=None):
    now = (now or datetime.now(VIETNAM_TZ)).astimezone(VIETNAM_TZ)
    raw = str(value or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"\d{10}(?:\.\d+)?|\d{13}", raw):
        try:
            stamp = float(raw) / (1000 if len(raw.split(".")[0]) == 13 else 1)
            point = datetime.fromtimestamp(stamp, VIETNAM_TZ)
            return PostDate(point, point, "timestamp")
        except (OverflowError, OSError, ValueError):
            return None
    if re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", raw):
        try:
            point = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            point = point.replace(tzinfo=VIETNAM_TZ) if point.tzinfo is None else point.astimezone(VIETNAM_TZ)
            return PostDate(point, point, "datetime")
        except ValueError:
            return None
    text = normalize_text(raw)
    if text in {"vua xong", "just now", "now"}:
        return PostDate(now - timedelta(minutes=1), now, "relative")
    relative = re.fullmatch(
        r"(\d+)\s*(giay|seconds?|secs?|s|phut|ph|minutes?|mins?|m|gio|hours?|hrs?|h|ngay|days?|d|tuan|weeks?|w|thang|months?|mo)(?:\s*(truoc|ago))?",
        text,
    )
    if relative:
        count, unit = int(relative.group(1)), relative.group(2)
        if unit in {"thang", "month", "months", "mo"}:
            return PostDate(now - timedelta(days=(count + 1) * 31), now - timedelta(days=count * 28), "relative")
        units = [
            ({"giay", "second", "seconds", "sec", "secs", "s"}, timedelta(seconds=1)),
            ({"phut", "ph", "minute", "minutes", "min", "mins", "m"}, timedelta(minutes=1)),
            ({"gio", "hour", "hours", "hr", "hrs", "h"}, timedelta(hours=1)),
            ({"ngay", "day", "days", "d"}, timedelta(days=1)),
            ({"tuan", "week", "weeks", "w"}, timedelta(weeks=1)),
        ]
        step = next(step for labels, step in units if unit in labels)
        return PostDate(now - (count + 1) * step, now - count * step, "relative")

    clock = re.search(r"(?<!\d)(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(am|pm)?", raw, re.I)
    hour, minute, second = 0, 0, 0
    if clock:
        hour, minute, second = int(clock.group(1)), int(clock.group(2)), int(clock.group(3) or 0)
        if clock.group(4):
            if not 1 <= hour <= 12:
                return None
            hour = hour % 12 + (12 if clock.group(4).lower() == "pm" else 0)
    day = month = year = None
    explicit_year = False
    if re.search(r"\b(hom nay|today)\b", text):
        day, month, year = now.day, now.month, now.year
    elif re.search(r"\b(hom qua|yesterday)\b", text):
        yesterday = now - timedelta(days=1)
        day, month, year = yesterday.day, yesterday.month, yesterday.year
    else:
        iso_day = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", raw)
        numeric = re.search(r"\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{4}))?\b", raw)
        vietnamese = re.search(r"\b(\d{1,2})\s*(?:thang|thg)\s*(\d{1,2})(?:\s*(?:nam\s*)?(\d{4}))?\b", text)
        if iso_day:
            year, month, day = map(int, iso_day.groups())
            explicit_year = True
        elif vietnamese or numeric:
            match = vietnamese or numeric
            day, month = int(match.group(1)), int(match.group(2))
            year = int(match.group(3)) if match.group(3) else now.year
            explicit_year = bool(match.group(3))
        else:
            months = {name: index for index, names in enumerate([
                ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"),
                ("may",), ("june", "jun"), ("july", "jul"), ("august", "aug"),
                ("september", "sep", "sept"), ("october", "oct"), ("november", "nov"), ("december", "dec"),
            ], 1) for name in names}
            month_pattern = "|".join(months)
            match = re.search(rf"\b({month_pattern}) (\d{{1,2}})(?: (\d{{4}}))?\b", text)
            reverse = re.search(rf"\b(\d{{1,2}}) ({month_pattern})(?: (\d{{4}}))?\b", text)
            if match:
                month, day = months[match.group(1)], int(match.group(2))
            elif reverse:
                month, day = months[reverse.group(2)], int(reverse.group(1))
                match = reverse
            if match:
                year = int(match.group(3)) if match.group(3) else now.year
                explicit_year = bool(match.group(3))
    if day is None:
        return None
    try:
        point = datetime(year, month, day, hour, minute, second, tzinfo=VIETNAM_TZ)
        if not explicit_year and point.date() > now.date():
            point = point.replace(year=year - 1)
        if clock:
            return PostDate(point, point, "datetime")
        return PostDate(point, min(now, point + timedelta(days=1) - timedelta(microseconds=1)), "day")
    except ValueError:
        return None
