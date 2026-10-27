import re
import time
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse

from playwright.sync_api import TimeoutError


class FacebookBrowser:

    def __init__(self, browser):
        self.browser = browser

    @property
    def page(self):
        return self.browser.page

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
        normalized = re.sub(r"\s+", " ", str(message)).casefold()
        return any(
            str(phrase).strip().casefold() in normalized
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

    def get_profile(self):

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

                if match:

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

                    if text:

                        name = text
                        break

            except Exception:
                pass

        # -----------------------------------------------------
        # Thử /me nếu chưa đủ thông tin
        # -----------------------------------------------------

        if not uid or not name:

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

        if not page.url or "facebook.com" not in page.url:

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
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
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

        submit.click(timeout=8000)
        page.wait_for_timeout(2500)
        return {
            "target_url": target_url,
            "submitted": True,
            "message": "Đã gửi bài lên Facebook. Nếu nhóm bật duyệt bài, bài có thể đang chờ quản trị viên.",
        }

    def find_buying_posts(
        self,
        source_url,
        phrases,
        max_posts=30,
        scroll_count=6,
        cancel_event=None,
    ):
        """Browse a Facebook feed/group and collect visible buyer-intent posts."""
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

        max_posts = max(1, min(int(max_posts), 100))
        page.goto(source_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)
        if not self.is_logged_in():
            raise RuntimeError("Profile này đã đăng xuất. Hãy đăng nhập lại trong Accounts.")

        posts = {}
        articles = page.locator('[role="article"]')

        for scroll_index in range(max(1, scroll_count)):
            if cancel_event is not None and cancel_event.is_set():
                break

            total = articles.count()
            for index in range(total):
                if cancel_event is not None and cancel_event.is_set():
                    break

                article = articles.nth(index)
                try:
                    message_locator = article.locator(
                        'div[data-ad-preview="message"]'
                    )
                    if message_locator.count():
                        message = message_locator.first.inner_text(timeout=2000)
                    else:
                        message = article.inner_text(timeout=2000)
                    message = re.sub(r"\s+", " ", message).strip()
                    if not message or not self.matches_buying_intent(message, phrases):
                        continue

                    links = article.locator(
                        'a[href*="/posts/"], a[href*="/permalink/"], '
                        'a[href*="story_fbid="]'
                    )
                    post_url = ""
                    for link_index in range(links.count()):
                        href = links.nth(link_index).get_attribute("href")
                        if href:
                            candidate = urljoin(
                                "https://www.facebook.com/", href
                            )
                            candidate_host = (
                                urlparse(candidate).hostname or ""
                            ).lower()
                            if (
                                candidate_host == "facebook.com"
                                or candidate_host.endswith(".facebook.com")
                            ):
                                post_url = candidate
                                break

                    if not post_url:
                        continue

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
                    posts[post_url] = {
                        "id": post_id,
                        "url": post_url,
                        "author": author,
                        "message": message,
                    }
                    if len(posts) >= max_posts:
                        break
                except Exception:
                    continue

            if len(posts) >= max_posts:
                break
            if scroll_index + 1 < scroll_count:
                page.mouse.wheel(0, 2400)
                page.wait_for_timeout(900)

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
        pieces = re.split(r"[\r\n·•]+", value)
        for piece in pieces:
            candidate = re.sub(r"\s+", " ", piece).strip(" \t:|-")
            candidate = re.sub(r"\s*\(\d+\)\s*$", "", candidate)
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

        page = self.page

        if page is None:
            raise RuntimeError(
                "Facebook page chưa được mở."
            )

        urls = ["https://www.facebook.com/groups/joins/"]
        groups = {}
        self.last_group_scan_complete = False
        self.last_group_scan_expected = None
        reached_bottom = False

        for target_url in urls:

            if cancel_event is not None and cancel_event.is_set():
                break

            try:

                page.goto(
                    target_url,
                    wait_until="domcontentloaded",
                    timeout=30000
                )

                page.wait_for_timeout(4000)
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
                            candidate = urljoin("https://www.facebook.com/", href)
                            parsed = urlparse(candidate)
                            host = (parsed.hostname or "").lower()
                            if host != "facebook.com" and not host.endswith(".facebook.com"):
                                continue
                            path_parts = [
                                unquote(part)
                                for part in parsed.path.split("/")
                                if part
                            ]
                            if len(path_parts) != 2 or path_parts[0].casefold() != "groups":
                                continue
                            group_id = path_parts[1].strip()
                            if (
                                not group_id
                                or group_id.casefold()
                                in {"feed", "joins", "discover", "search", "create"}
                                or not re.fullmatch(r"[\w.-]+", group_id, flags=re.UNICODE)
                            ):
                                continue

                            name = self._get_group_name_from_link(link)
                            if not name:
                                continue
                            group_url = (
                                "https://www.facebook.com/groups/"
                                f"{quote(group_id, safe='._-')}/"
                            )
                            groups[group_url] = {
                                "id": group_id,
                                "name": name,
                                "url": group_url,
                            }
                        except Exception:
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

                print(
                    f"Group page error: {e}"
                )

        expected = self.last_group_scan_expected
        self.last_group_scan_complete = reached_bottom and (
            expected is None or len(groups) >= expected
        )
        return list(groups.values())
