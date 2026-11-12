import re
import time
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urljoin, urlparse

from playwright.sync_api import Error as PlaywrightError, TimeoutError
from backend.utils.text_matching import normalize_text
from backend.facebook.parsers.group_parser import normalize_group_url
from backend.services.comment_rules import contains_phrase, post_identity
from backend.facebook.parsers.post_date import parse_post_date, VIETNAM_TZ


class FacebookBrowser:

    def __init__(self, browser):
        self.browser = browser

    @property
    def page(self):
        return self.browser.page

    def dismiss_group_welcome(self, cancel_event=None):
        """Close only a recognized group welcome card, using its own close button."""
        page = self.page
        if page is None or not urlparse(page.url).path.startswith("/groups/"):
            return 0
        greeting = re.compile(r"^(?:.{0,100}\b)?(?:chao mung ban (?:den|tham gia)|welcome (?:to|back to|you to))\b")
        close_name = re.compile(r"^(?:đóng|đóng hộp thoại|close|close dialog|dismiss)$", re.I)
        dismissed = 0
        for _ in range(3):
            if cancel_event is not None and cancel_event.is_set():
                break
            closed = False
            dialogs = page.locator('[role="dialog"], [role="alertdialog"]')
            for index in range(min(dialogs.count(), 10)):
                try:
                    dialog = dialogs.nth(index)
                    if not dialog.is_visible():
                        continue
                    # Never dismiss a composer, login form, or verification form.
                    if dialog.locator('textarea, input, [contenteditable="true"], [role="textbox"]').count():
                        continue
                    intro = normalize_text(dialog.inner_text(timeout=800)[:500])
                    if not greeting.search(intro):
                        continue
                    buttons = dialog.get_by_role("button", name=close_name)
                    for button_index in range(buttons.count()):
                        button = buttons.nth(button_index)
                        if not (button.is_visible() and button.is_enabled()):
                            continue
                        if cancel_event is not None and cancel_event.is_set():
                            return dismissed
                        button.click(timeout=1500)
                        dialog.wait_for(state="hidden", timeout=1500)
                        dismissed += 1
                        closed = True
                        break
                    if closed:
                        break
                except PlaywrightError:
                    # Facebook may re-render a card while its close control is read.
                    continue
            if not closed:
                break
        return dismissed

    # =========================================================
    # LOGIN
    # =========================================================

    def is_logged_in(self):

        try:
            page = self.page

            if page is None:
                return False

            url = page.url.lower()

            if "login" in url:
                return False

            if "checkpoint" in url:
                return False

            # Kiểm tra các dấu hiệu đã đăng nhập
            # c_user is a strong sign of an authenticated Facebook session.
            # Generic navigation elements can also appear while logged out.
            context = getattr(self.browser, "context", None)
            if context is not None:
                try:
                    cookies = context.cookies("https://www.facebook.com")
                    if any(
                        cookie.get("name") == "c_user"
                        and str(cookie.get("value", "")).isdigit()
                        for cookie in cookies
                    ):
                        return True
                except Exception:
                    pass

            selectors = [
                '[aria-label="Trang chủ"]',
                '[aria-label="Home"]',
            ]

            for selector in selectors:

                try:

                    if page.locator(selector).count() > 0:
                        return True

                except Exception:
                    pass

            return False

        except Exception:

            return False

    @staticmethod
    def matches_buying_intent(message, phrases):
        return any(
            contains_phrase(message, phrase)
            for phrase in phrases
            if str(phrase).strip()
        )

    def wait_for_login(self, timeout=300, poll_interval=2, cancel_event=None):
        """Wait for the user to finish logging in to Facebook.

        The browser remains open so the user can complete any manual steps,
        including a checkpoint or two-factor prompt. Returns False on timeout.
        """
        if timeout <= 0:
            raise ValueError("timeout phải lớn hơn 0")
        if poll_interval <= 0:
            raise ValueError("poll_interval phải lớn hơn 0")

        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                return False

            if self.is_logged_in():
                session = getattr(self.browser, "session", None)
                if session is not None:
                    session.logged_in = True
                return True

            delay = min(poll_interval, max(0, deadline - time.monotonic()))
            if cancel_event is not None:
                cancel_event.wait(delay)
            else:
                time.sleep(delay)

        return False

    # =========================================================
    # PROFILE
    # =========================================================

    def get_profile(self, allow_navigation=True):

        page = self.page

        if page is None:
            raise RuntimeError(
                "Facebook page chưa được mở."
            )

        # -----------------------------------------------------
        # Lấy thông tin từ trang hiện tại trước
        # -----------------------------------------------------

        uid = ""
        name = ""

        # c_user remains available when Facebook changes its serialized HTML.
        try:
            context = getattr(self.browser, "context", None)
            if context is not None:
                for cookie in context.cookies("https://www.facebook.com"):
                    if cookie.get("name") == "c_user":
                        candidate = str(cookie.get("value", ""))
                        if candidate.isdigit():
                            uid = candidate
                        break
        except Exception:
            pass

        try:

            html = page.content()

            patterns = [
                r'"USER_ID":"(\d+)"',
                r'"userID":"(\d+)"',
                r'"user_id":"(\d+)"',
                r'"actorID":"(\d+)"',
                r'"actor_id":"(\d+)"',
                r'"profile_id":"(\d+)"',
            ]

            for pattern in patterns:

                match = re.search(
                    pattern,
                    html
                )

                if match and not uid:

                    uid = match.group(1)
                    break

        except Exception:
            pass

        # -----------------------------------------------------
        # Lấy tên
        # -----------------------------------------------------

        selectors = [
            "h1",
            '[role="main"] h1',
        ]

        for selector in selectors:

            try:

                locator = page.locator(
                    selector
                )

                if locator.count() > 0:

                    text = (
                        locator.first
                        .inner_text()
                        .strip()
                    )

                    if text and text.casefold() not in {"trang chủ", "home", "facebook", "nhóm", "groups"}:

                        name = text
                        break

            except Exception:
                pass

        # -----------------------------------------------------
        # Thử /me nếu chưa đủ thông tin
        # -----------------------------------------------------

        if allow_navigation and (not uid or not name):

            current_url = page.url

            try:

                page.goto(
                    "https://www.facebook.com/me",
                    wait_until="domcontentloaded",
                    timeout=30000
                )

                page.wait_for_timeout(2500)

                url = page.url.lower()

                # Không được lấy "www.facebook.com" làm UID
                if (
                    "login" not in url
                    and "checkpoint" not in url
                ):

                    try:

                        html = page.content()

                        patterns = [
                            r'"USER_ID":"(\d+)"',
                            r'"userID":"(\d+)"',
                            r'"user_id":"(\d+)"',
                            r'"profile_id":"(\d+)"',
                        ]

                        for pattern in patterns:

                            match = re.search(
                                pattern,
                                html
                            )

                            if match:

                                uid = match.group(1)
                                break

                    except Exception:
                        pass

                    for selector in selectors:

                        try:

                            locator = page.locator(
                                selector
                            )

                            if locator.count() > 0:

                                text = (
                                    locator.first
                                    .inner_text()
                                    .strip()
                                )

                                if text:

                                    name = text
                                    break

                        except Exception:
                            pass

            except Exception:
                pass

        # -----------------------------------------------------
        # Restore page if necessary
        # -----------------------------------------------------

        if allow_navigation and (not page.url or "facebook.com" not in page.url):

            try:
                page.goto(
                    "https://www.facebook.com/",
                    wait_until="domcontentloaded",
                    timeout=30000
                )
            except Exception:
                pass

        if uid and not uid.isdigit():
            uid = ""

        return {
            "uid": uid,
            "name": name,
            "url": page.url
        }

    def publish_post(self, target_url, message, media_paths=(), cancel_event=None):
        """Submit one user-confirmed post to a profile feed or Facebook group."""
        page = self.page
        if page is None:
            raise RuntimeError("Facebook page chưa được mở.")
        message = str(message or "").strip()
        media_paths = [str(Path(path).resolve()) for path in media_paths if str(path).strip()]
        if not message and not media_paths:
            raise ValueError("Bài đăng cần có nội dung hoặc ảnh/video.")

        parsed = urlparse(target_url)
        host = (parsed.hostname or "").lower()
        if host != "facebook.com" and not host.endswith(".facebook.com"):
            raise ValueError("Đích đăng không thuộc Facebook.")
        if not self.is_logged_in():
            raise RuntimeError("Profile này chưa đăng nhập Facebook.")
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Đã dừng yêu cầu đăng bài.")

        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1600)
        if not self.is_logged_in():
            raise RuntimeError("Facebook yêu cầu đăng nhập lại hoặc xác minh tài khoản.")

        self.dismiss_group_welcome(cancel_event)

        composer_pattern = re.compile(
            r"(?:bạn viết gì|bạn đang nghĩ gì|viết bài|tạo bài viết|write something|what's on your mind|create post)",
            re.IGNORECASE,
        )
        composer_opened = False
        for locator in (
            page.get_by_role("button", name=composer_pattern),
            page.locator('[role="button"]').filter(has_text=composer_pattern),
        ):
            for index in range(locator.count()):
                candidate = locator.nth(index)
                try:
                    if candidate.is_visible() and candidate.is_enabled():
                        candidate.click(timeout=5000)
                        composer_opened = True
                        break
                except Exception:
                    continue
            if composer_opened:
                break
        if not composer_opened:
            raise RuntimeError("Không tìm thấy nút tạo bài viết trên trang Facebook này.")

        page.wait_for_timeout(900)
        dialogs = page.locator('[role="dialog"]')
        composer = dialogs.last if dialogs.count() else page
        editors = composer.locator(
            '[contenteditable="true"][role="textbox"], textarea[role="textbox"]'
        )
        editor = None
        for index in range(editors.count()):
            candidate = editors.nth(index)
            try:
                if candidate.is_visible() and candidate.is_enabled():
                    editor = candidate
                    break
            except Exception:
                continue
        if editor is None:
            raise RuntimeError("Facebook chưa mở được ô nhập nội dung bài viết.")
        if message:
            editor.fill(message, timeout=5000)

        if media_paths:
            for media_path in media_paths:
                if not Path(media_path).is_file():
                    raise FileNotFoundError(f"Không tìm thấy tệp media: {media_path}")
            file_inputs = composer.locator('input[type="file"]')
            if not file_inputs.count():
                file_inputs = page.locator('input[type="file"]')
            if not file_inputs.count():
                raise RuntimeError("Không tìm thấy bộ chọn ảnh/video trong trình đăng bài.")
            attached = False
            for index in range(file_inputs.count()):
                try:
                    file_inputs.nth(index).set_input_files(media_paths, timeout=10000)
                    attached = True
                    break
                except Exception:
                    continue
            if not attached:
                raise RuntimeError("Facebook không nhận được ảnh/video đã chọn.")

        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Đã dừng yêu cầu đăng bài trước khi gửi.")

        submit_pattern = re.compile(r"^(?:đăng|post)$", re.IGNORECASE)
        submit = None
        clock = getattr(cancel_event, "active_time", time.monotonic)
        deadline = clock() + 45
        while clock() < deadline:
            for index in range(composer.get_by_role("button", name=submit_pattern).count()):
                candidate = composer.get_by_role("button", name=submit_pattern).nth(index)
                try:
                    if candidate.is_visible() and candidate.is_enabled():
                        submit = candidate
                        break
                except Exception:
                    continue
            if submit is not None:
                break
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError("Đã dừng yêu cầu đăng bài trước khi gửi.")
            page.wait_for_timeout(500)
        if submit is None:
            raise RuntimeError("Không tìm thấy nút Đăng hoặc Facebook chưa xử lý xong media.")

        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Đã dừng yêu cầu đăng bài trước khi gửi.")
        submit.click(timeout=8000)
        page.wait_for_timeout(2500)
        return {
            "target_url": target_url,
            "submitted": True,
            "message": "Đã gửi bài lên Facebook. Nếu nhóm bật duyệt bài, bài có thể đang chờ quản trị viên.",
        }

    def _read_post_date(self, links, now, days):
        dates = []
        for link in links:
            nodes = [link]
            try:
                nested = link.locator("time, abbr, [data-utime]")
                nodes.extend(nested.nth(index) for index in range(min(nested.count(), 4)))
            except Exception:
                pass
            for node in nodes:
                for attribute in ("data-utime", "datetime", "title", "aria-label"):
                    try:
                        parsed = parse_post_date(node.get_attribute(attribute), now)
                        if parsed:
                            dates.append(parsed)
                    except Exception:
                        continue
                try:
                    parsed = parse_post_date(node.inner_text(timeout=800), now)
                    if parsed:
                        dates.append(parsed)
                except Exception:
                    pass
        best = min(dates, key=lambda date: date.newest - date.oldest) if dates else None
        if best and best.classification(now, days) != "uncertain":
            return best
        # Facebook often exposes the full publication date only on hover.
        for link in links[:3]:
            try:
                link.hover(timeout=1200)
                self.page.wait_for_timeout(250)
                tooltips = self.page.get_by_role("tooltip")
                for index in range(tooltips.count()):
                    tooltip = tooltips.nth(index)
                    if not tooltip.is_visible():
                        continue
                    parsed = parse_post_date(tooltip.inner_text(timeout=800), now)
                    if parsed and parsed.classification(now, days) != "uncertain":
                        return parsed
            except Exception:
                continue
        return best

    @staticmethod
    def _scroll_post_feed(page):
        try:
            page.evaluate("""() => {
                const root = document.querySelector('[role="main"]') || document.querySelector('main') || document.body;
                const articles = [...root.querySelectorAll('[role="article"]')];
                const visible = articles.find(el => {
                    const rect = el.getBoundingClientRect();
                    return rect.bottom > 0 && rect.top < innerHeight;
                }) || articles[0] || root;
                let node = visible.parentElement;
                while (node && node !== document.body) {
                    const style = getComputedStyle(node);
                    if (/(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight + 40) {
                        node.scrollBy(0, Math.max(600, node.clientHeight * 0.8));
                        return;
                    }
                    node = node.parentElement;
                }
                const scroller = document.scrollingElement || document.documentElement;
                scroller.scrollBy(0, Math.max(600, innerHeight * 0.8));
            }""")
        except Exception:
            page.mouse.wheel(0, 1600)

    def find_buying_posts(
        self,
        source_url,
        phrases,
        max_posts=30,
        scroll_count=80,
        cancel_event=None,
        message_filter=None,
        max_age_days=15,
        now=None,
        max_seconds=120,
        group_only=False,
        progress_callback=None,
    ):
        """Collect recent buyer posts; never infer a date from comment timestamps."""
        page = self.page
        if page is None:
            raise RuntimeError("Facebook page chưa được mở.")

        parsed_source = urlparse(source_url)
        if parsed_source.scheme not in {"http", "https"} or not (
            (parsed_source.hostname or "").lower() == "facebook.com"
            or (parsed_source.hostname or "").lower().endswith(".facebook.com")
        ):
            raise ValueError("Nguồn bài viết phải là URL Facebook.")

        phrases = [str(value).strip().casefold() for value in phrases if str(value).strip()]
        if not phrases:
            raise ValueError("Hãy nhập ít nhất một cụm từ thể hiện nhu cầu mua.")

        group_url = normalize_group_url(source_url) if group_only else None
        group_id = urlparse(group_url).path.split("/")[2] if group_url else None
        now = (now or datetime.now(VIETNAM_TZ)).astimezone(VIETNAM_TZ)
        max_age_days = max(1, min(int(max_age_days), 15))
        max_posts = max(1, min(int(max_posts), 500))
        scroll_count = max(1, min(int(scroll_count), 300))
        clock = getattr(cancel_event, "active_time", time.monotonic)
        deadline = clock() + max(1, min(float(max_seconds), 600))
        stats = self.last_post_scan_stats = dict(
            seen_posts=0, found=0, skipped_old=0, skipped_unknown_date=0,
            skipped_future=0, scrolls=0, reason="max_scrolls", max_age_days=max_age_days,
            cutoff=(now - timedelta(days=max_age_days)).isoformat(),
        )
        if cancel_event is not None and cancel_event.is_set():
            stats["reason"] = "cancelled"
            return []
        target_url = group_url + "?sorting_setting=CHRONOLOGICAL" if group_url else source_url
        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)
        if not self.is_logged_in():
            raise RuntimeError("Profile này đã đăng xuất. Hãy đăng nhập lại trong Accounts.")
        self.dismiss_group_welcome(cancel_event)
        if group_url:
            try:
                resolved_group = normalize_group_url(page.url)
            except ValueError:
                raise RuntimeError("Facebook không mở đúng trang nhóm. Kiểm tra quyền truy cập nhóm rồi thử lại.") from None
            group_ids = {group_id, urlparse(resolved_group).path.split("/")[2]}
        else:
            group_ids = set()

        posts = {}
        observed, processed, old_urls, undated_urls, future_urls = set(), set(), set(), set(), set()
        date_attempts = {}
        stalled = 0
        articles = page.locator('[role="article"]')

        for scroll_index in range(scroll_count):
            if cancel_event is not None and cancel_event.is_set():
                stats["reason"] = "cancelled"
                break
            self.dismiss_group_welcome(cancel_event)
            if clock() >= deadline:
                stats["reason"] = "time_budget"
                break

            before_count = len(observed)
            total = articles.count()
            for index in range(total):
                if cancel_event is not None and cancel_event.is_set():
                    stats["reason"] = "cancelled"
                    break
                if clock() >= deadline:
                    stats["reason"] = "time_budget"
                    break

                article = articles.nth(index)
                try:
                    links = article.locator(
                        'a[href*="/posts/"], a[href*="/permalink/"], a[href*="story_fbid="]'
                    )
                    post_url, date_links = "", []
                    for link_index in range(links.count()):
                        link = links.nth(link_index)
                        href = link.get_attribute("href")
                        if not href:
                            continue
                        candidate = urljoin("https://www.facebook.com/", href)
                        parsed = urlparse(candidate)
                        host = (parsed.hostname or "").lower()
                        if parsed.scheme not in {"http", "https"} or (host != "facebook.com" and not host.endswith(".facebook.com")):
                            continue
                        if {"comment_id", "reply_comment_id"} & parse_qs(parsed.query).keys():
                            continue
                        if group_ids:
                            path_match = re.match(r"^/groups/([^/]+)/(?:posts|permalink)/[^/]+", parsed.path)
                            if not path_match or path_match.group(1) not in group_ids:
                                continue
                        candidate = post_identity(candidate)
                        if not post_url:
                            post_url = candidate
                        if candidate == post_url:
                            date_links.append(link)
                    if not post_url:
                        continue
                    is_new = post_url not in observed
                    observed.add(post_url)
                    if is_new and len(observed) % 10 == 0 and progress_callback:
                        stats.update(seen_posts=len(observed), found=len(posts), skipped_old=len(old_urls),
                                     skipped_unknown_date=len(undated_urls), skipped_future=len(future_urls), scrolls=scroll_index + 1)
                        progress_callback(dict(stats))
                    if post_url in processed:
                        continue
                    message_locator = article.locator(
                        'div[data-ad-preview="message"]'
                    )
                    if message_locator.count():
                        message = message_locator.first.inner_text(timeout=2000)
                    else:
                        message_locator = article.locator('[data-ad-comet-preview="message"]')
                        if not message_locator.count():
                            # An entire article can include buyer keywords in its
                            # comments; those must not be mistaken for the post.
                            continue
                        message = message_locator.first.inner_text(timeout=2000)
                    message = re.sub(r"\s+", " ", message).strip()
                    if not message or not self.matches_buying_intent(message, phrases):
                        processed.add(post_url)
                        continue
                    if message_filter is not None and not message_filter(message):
                        processed.add(post_url)
                        continue
                    published = self._read_post_date(date_links, now, max_age_days)
                    classification = published.classification(now, max_age_days) if published else "uncertain"
                    if classification != "recent":
                        if classification == "old":
                            old_urls.add(post_url)
                            processed.add(post_url)
                        elif classification == "future":
                            future_urls.add(post_url)
                            processed.add(post_url)
                        else:
                            undated_urls.add(post_url)
                            date_attempts[post_url] = date_attempts.get(post_url, 0) + 1
                            if date_attempts[post_url] >= 2:
                                processed.add(post_url)
                        continue
                    undated_urls.discard(post_url)
                    processed.add(post_url)

                    author = "Facebook user"
                    author_links = article.locator("h2 a, h3 a")
                    if author_links.count():
                        author = (
                            author_links.first.inner_text(timeout=1000).strip()
                            or author
                        )

                    query = parse_qs(urlparse(post_url).query)
                    post_match = re.search(
                        r"/(?:posts|permalink)/([^/?#]+)",
                        urlparse(post_url).path,
                    )
                    post_id = (
                        post_match.group(1)
                        if post_match
                        else (query.get("story_fbid") or [""])[0]
                    )
                    display = published.oldest.strftime("%d/%m/%Y %H:%M")
                    if published.precision == "day":
                        display = published.oldest.strftime("%d/%m/%Y")
                    elif published.precision == "relative":
                        display = (published.oldest.strftime("%d/%m") + " – " + published.newest.strftime("%d/%m/%Y")
                                   if published.newest - published.oldest >= timedelta(days=1) else "≈ " + display)
                    posts[post_url] = {
                        "id": post_id,
                        "url": post_url,
                        "author": author,
                        "message": message,
                        "published_at": published.oldest.isoformat(),
                        "published_until": published.newest.isoformat(),
                        "published_precision": published.precision,
                        "published_display": display,
                        "source_url": group_url or source_url,
                    }
                    if len(posts) >= max_posts:
                        break
                except Exception:
                    continue

            stalled = stalled + 1 if len(observed) == before_count else 0
            stats.update(seen_posts=len(observed), found=len(posts), skipped_old=len(old_urls),
                         skipped_unknown_date=len(undated_urls), skipped_future=len(future_urls), scrolls=scroll_index + 1)
            if len(posts) >= max_posts:
                stats["reason"] = "post_limit"
            if progress_callback:
                progress_callback(dict(stats))
            if len(posts) >= max_posts or stats["reason"] in {"cancelled", "time_budget"}:
                break
            # Pinned and out-of-order posts are common: an old post alone must
            # never stop a scan. Stop only after repeated absence of new IDs.
            if stalled >= 10:
                stats["reason"] = "no_new_posts"
                break
            if scroll_index + 1 < scroll_count:
                self._scroll_post_feed(page)
                page.wait_for_timeout(1000)

        return list(posts.values())

    def comment_on_post(self, post_url, message):
        """Submit a comment through the logged-in browser session."""
        page = self.page
        if page is None:
            raise RuntimeError("Facebook page chưa được mở.")
        if not message or not message.strip():
            raise ValueError("Nội dung bình luận không được để trống.")

        parsed = urlparse(post_url)
        post_host = (parsed.hostname or "").lower()
        if post_host != "facebook.com" and not post_host.endswith(".facebook.com"):
            raise ValueError("Link bài viết không thuộc Facebook.")

        page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1200)
        if not self.is_logged_in():
            raise RuntimeError("Profile này đã đăng xuất. Hãy đăng nhập lại trong Accounts.")

        articles = page.locator('[role="article"]')
        for article_index in reversed(range(articles.count())):
            editors = articles.nth(article_index).locator(
                '[contenteditable="true"][role="textbox"]'
            )
            for index in range(editors.count()):
                editor = editors.nth(index)
                try:
                    if not editor.is_visible():
                        continue
                    editor.fill(message.strip(), timeout=3000)
                    editor.press("Enter")
                    page.wait_for_timeout(1200)
                    if editor.inner_text(timeout=1000).strip() == message.strip():
                        raise RuntimeError("Facebook chưa xác nhận gửi bình luận.")
                    return {"url": post_url, "sent": True}
                except RuntimeError:
                    raise
                except Exception:
                    continue

        for selector in (
            '[contenteditable="true"][role="textbox"][aria-label*="comment" i]',
            '[contenteditable="true"][role="textbox"][aria-label*="bình luận" i]',
        ):
            editor = page.locator(selector).first
            try:
                if not editor.is_visible():
                    continue
                editor.fill(message.strip(), timeout=3000)
                editor.press("Enter")
                page.wait_for_timeout(1200)
                if editor.inner_text(timeout=1000).strip() == message.strip():
                    raise RuntimeError("Facebook chưa xác nhận gửi bình luận.")
                return {"url": post_url, "sent": True}
            except RuntimeError:
                raise
            except Exception:
                continue

        raise RuntimeError(
            "Không tìm thấy ô bình luận. Hãy mở bài viết và kiểm tra quyền của tài khoản."
        )

    # =========================================================
    # GROUPS
    # =========================================================

    @staticmethod
    def _is_group_time_label(value):
        value = re.sub(r"\s+", " ", str(value or "")).strip().casefold()
        if not value:
            return True
        if value in {"vừa xong", "hôm qua", "just now", "yesterday"}:
            return True
        return bool(
            re.fullmatch(
                r"\d+\s*(?:phút|ph|giờ|ngày|tuần|tháng|năm|minutes?|mins?|hours?|days?|weeks?|months?|years?)(?:\s*(?:trước|ago))?",
                value,
            )
        )

    @classmethod
    def _clean_group_name(cls, value):
        value = re.sub(
            r"\s*(?:Lần hoạt động gần nhất|Last active)\s*:?\s*.*$",
            "",
            str(value or ""),
            flags=re.IGNORECASE | re.DOTALL,
        )
        pieces = re.split(r"[\r\n]+", value)
        for piece in pieces:
            candidate = re.sub(r"\s+", " ", piece).strip(" \t:|-")
            for separator in (" · ", " • "):
                name, found, suffix = candidate.rpartition(separator)
                if found and cls._is_group_time_label(suffix):
                    candidate = name.strip()
            if candidate and not cls._is_group_time_label(candidate):
                if candidate.casefold() not in {
                    "groups",
                    "facebook groups",
                    "see all",
                    "xem tất cả",
                    "nhóm",
                    "xem nhóm",
                    "see group",
                    "view group",
                    "xem thêm",
                    "see more",
                    "your groups",
                    "groups you manage",
                    "nhóm của bạn",
                    "các nhóm của bạn",
                    "nhóm bạn đã tham gia",
                    "tất cả các nhóm bạn đã tham gia",
                    "all groups you have joined",
                    "all groups you've joined",
                    "join group",
                    "join this group",
                    "tham gia nhóm",
                }:
                    return candidate
        return ""

    @classmethod
    def _get_group_name_from_link(cls, link):
        candidates = []
        for attribute in ("aria-label", "title"):
            try:
                candidates.append(link.get_attribute(attribute) or "")
            except Exception:
                pass
        try:
            candidates.append(link.inner_text(timeout=1500))
        except Exception:
            pass

        for candidate in candidates:
            name = cls._clean_group_name(candidate)
            if name:
                return name
        return ""

    @staticmethod
    def _open_all_joined_groups(page):
        pattern = re.compile(
            r"(?:tất cả các nhóm bạn đã tham gia|all groups (?:you have|you've) joined)",
            re.IGNORECASE,
        )
        matches = page.get_by_text(pattern)
        for index in range(matches.count()):
            item = matches.nth(index)
            try:
                if not item.is_visible():
                    continue
                href = item.evaluate(
                    "el => (el.closest('a[href]') || (el.matches('a[href]') ? el : null))?.href || ''"
                )
                if href:
                    target = urljoin("https://www.facebook.com/", href)
                    parsed = urlparse(target)
                    if (
                        parsed.scheme != "https"
                        or parsed.hostname not in {"www.facebook.com", "facebook.com"}
                        or parsed.path.rstrip("/") != "/groups/joins"
                    ):
                        continue
                    if target.rstrip("/") != page.url.rstrip("/"):
                        page.goto(target, wait_until="domcontentloaded", timeout=30000)
                    else:
                        item.click(timeout=4000)
                else:
                    item.click(timeout=4000)
                page.wait_for_timeout(1800)
                return True
            except Exception:
                continue
        return False

    @staticmethod
    def _expand_group_list(main, page):
        more_pattern = re.compile(r"^(?:xem thêm|see more)$", re.IGNORECASE)
        for _ in range(20):
            matches = main.get_by_text(more_pattern)
            clicked = False
            for index in range(matches.count()):
                item = matches.nth(index)
                try:
                    if not item.is_visible():
                        continue
                    item.click(timeout=2500)
                    page.wait_for_timeout(300)
                    clicked = True
                    break
                except Exception:
                    continue
            if not clicked:
                break

    @staticmethod
    def _expected_joined_group_count(page):
        try:
            text = page.locator("body").inner_text(timeout=3000)
        except Exception:
            return None
        match = re.search(
            r"(?:tất cả các nhóm bạn đã tham gia|all groups (?:you have|you've) joined)\s*\(([\d.,]+)\)",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        digits = re.sub(r"\D", "", match.group(1))
        return int(digits) if digits else None

    def get_groups(self, cancel_event=None):
        self.last_group_scan_complete = False
        self.last_group_scan_expected = None
        page = self.page

        if page is None:
            raise RuntimeError(
                "Facebook page chưa được mở."
            )

        urls = ["https://www.facebook.com/groups/joins/"]
        groups = {}
        reached_bottom = False
        extraction_failed = False
        unnamed_urls = set()

        for target_url in urls:

            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError("Đã dừng quét nhóm.")

            try:

                page.goto(
                    target_url,
                    wait_until="domcontentloaded",
                    timeout=30000
                )

                page.wait_for_timeout(4000)
                if not self.is_logged_in():
                    raise RuntimeError("Facebook đã đăng xuất hoặc yêu cầu xác minh. Hãy kiểm tra trong Accounts.")
                parsed_page = urlparse(page.url)
                if (
                    parsed_page.hostname not in {"facebook.com", "www.facebook.com"}
                    or parsed_page.path.rstrip("/") != "/groups/joins"
                ):
                    raise RuntimeError("Facebook không mở danh sách nhóm đã tham gia; giữ nguyên dữ liệu cũ.")
                self.last_group_scan_expected = self._expected_joined_group_count(page)
                self._open_all_joined_groups(page)
                if self.last_group_scan_expected is None:
                    self.last_group_scan_expected = self._expected_joined_group_count(page)

                main = page.locator('[role="main"]')
                if not main.count():
                    main = page.locator("main")
                if not main.count():
                    raise RuntimeError("Không tìm thấy danh sách nhóm Facebook trên trang.")
                self._expand_group_list(main.first, page)
                links = main.first.locator('a[href*="/groups/"]')
                previous_group_count = -1
                no_new_group_rounds = 0
                at_bottom_rounds = 0
                for _ in range(240):
                    if cancel_event is not None and cancel_event.is_set():
                        break

                    self._expand_group_list(main.first, page)
                    total = links.count()
                    for i in range(total):
                        if cancel_event is not None and cancel_event.is_set():
                            break
                        try:
                            link = links.nth(i)
                            href = link.get_attribute("href")
                            if not href:
                                continue
                            try:
                                group_url = normalize_group_url(href)
                            except ValueError:
                                continue
                            group_id = group_url.rstrip("/").rsplit("/", 1)[-1]
                            name = self._get_group_name_from_link(link)
                            if not name:
                                unnamed_urls.add(group_url)
                                continue
                            groups[group_url] = {
                                "id": group_id,
                                "name": name,
                                "url": group_url,
                            }
                        except Exception:
                            extraction_failed = True
                            continue

                    if len(groups) == previous_group_count:
                        no_new_group_rounds += 1
                    else:
                        no_new_group_rounds = 0
                        previous_group_count = len(groups)

                    scroll_state = main.first.evaluate(
                        """root => {
                            const targets = new Set();
                            const docScroller = document.scrollingElement;
                            if (docScroller) targets.add(docScroller);
                            targets.add(root);
                            const groupLinks = root.querySelectorAll('a[href*="/groups/"]');
                            for (const link of groupLinks) {
                                let node = link.parentElement;
                                while (node && node !== root.parentElement) {
                                    const style = getComputedStyle(node);
                                    const canScroll = /(auto|scroll|hidden)/.test(style.overflowY)
                                        && node.scrollHeight > node.clientHeight + 40;
                                    if (canScroll) {
                                        targets.add(node);
                                        break;
                                    }
                                    if (node === root) break;
                                    node = node.parentElement;
                                }
                            }
                            let moved = false;
                            let atBottom = true;
                            for (const node of targets) {
                                const maxTop = Math.max(0, node.scrollHeight - node.clientHeight);
                                if (maxTop <= 40) continue;
                                const before = node.scrollTop;
                                node.scrollTop = Math.min(maxTop, before + Math.max(500, node.clientHeight * 0.8));
                                if (node.scrollTop > before + 2) moved = true;
                                if (node.scrollTop < maxTop - 40) atBottom = false;
                            }
                            return {moved, atBottom};
                        }"""
                    )
                    if scroll_state.get("atBottom"):
                        at_bottom_rounds += 1
                    else:
                        at_bottom_rounds = 0

                    # The page virtualizes group cards, so the number of DOM
                    # links can stay fixed while new group IDs appear on scroll.
                    if no_new_group_rounds >= 8 and at_bottom_rounds >= 3:
                        reached_bottom = True
                        break
                    page.wait_for_timeout(550)

            except Exception as e:
                raise RuntimeError(f"Không quét được danh sách nhóm: {e}") from e

        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Đã dừng quét nhóm.")
        expected = self.last_group_scan_expected
        self.last_group_scan_complete = bool(
            reached_bottom
            and not extraction_failed
            and not (unnamed_urls - groups.keys())
            and expected is not None
            and len(groups) == expected
        )
        return list(groups.values())
