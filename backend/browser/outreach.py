"""Browser actions for explicitly selected outreach targets. No unattended login."""
import re
import json
import time
from urllib.parse import parse_qs, quote, urljoin, urlparse

from backend.services.outreach_service import normalize_target
from backend.services.comment_rules import post_identity
from backend.utils.text_matching import normalize_text
from playwright.sync_api import Error as PlaywrightError


class OutreachNeedsReview(RuntimeError):
    """The page needs user input, or a submitted action cannot be verified."""


class OutreachBrowser:
    def __init__(self, facebook):
        self.facebook = facebook
        self.mutated = False

    @property
    def page(self):
        return self.facebook.page

    @staticmethod
    def checkpoint(cancel):
        if cancel is not None and cancel.is_set():
            raise InterruptedError('Đã dừng tác vụ.')

    def open(self, url, cancel=None):
        self.checkpoint(cancel)
        if self.page is None:
            raise RuntimeError('Profile chưa được mở.')
        self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
        self.page.wait_for_timeout(1000)
        self.checkpoint(cancel)
        if not self.facebook.is_logged_in():
            raise RuntimeError('Profile đã đăng xuất hoặc đang yêu cầu xác minh.')

    def main(self):
        main = self.page.locator('[role="main"], main')
        if not main.count():
            raise RuntimeError('Không tìm thấy nội dung chính của trang Facebook.')
        return main.first

    def button(self, root, pattern):
        matches = root.get_by_role('button', name=re.compile(pattern, re.I))
        for index in range(matches.count()):
            if matches.nth(index).is_visible():
                return matches.nth(index)
        return None

    def discover(self, kind, query, industry='', region='', limit=50, cancel=None, progress=None):
        if kind not in {'group', 'person'} or not ' '.join((query, industry, region)).strip():
            raise ValueError('Chọn tìm nhóm/người và nhập ngành, khu vực hoặc từ khóa.')
        terms = ' '.join(dict.fromkeys(x.strip() for x in (query, industry, region) if x.strip()))
        path = 'groups' if kind == 'group' else 'people'
        self.open(f'https://www.facebook.com/search/{path}/?q={quote(terms)}', cancel)
        clock = getattr(cancel, 'active_time', time.monotonic)
        deadline = clock() + 120
        results, stalled = {}, 0
        for round_index in range(20):
            if cancel is not None and cancel.is_set():
                return list(results.values())
            if clock() >= deadline:
                break
            before = len(results)
            root = self.main()
            links = root.locator('a[href*="/groups/"]' if kind == 'group' else 'a[href]')
            for index in range(min(links.count(), 400)):
                if cancel is not None and cancel.is_set():
                    return list(results.values())
                link = links.nth(index)
                try:
                    href = urljoin('https://www.facebook.com/', link.get_attribute('href') or '')
                    url = normalize_target(kind, href)
                    raw = link.evaluate('''el => {
                        const card = el.closest('[role="article"], [role="listitem"]');
                        const name = (el.innerText || el.getAttribute('aria-label') || '').trim().split('\\n')[0];
                        return {name, card: Boolean(card), description: (card?.innerText || '').slice(0, 800)};
                    }''')
                    if (not raw['name'] or kind == 'person' and not raw['card']
                            or normalize_text(raw['name']) in {'xem nhom', 'view group', 'join group', 'tham gia nhom', 'add friend', 'ket ban'}):
                        continue
                    results.setdefault(url, dict(kind=kind, url=url, name=raw['name'], industry=industry,
                                                 region=region, description=raw['description'], joined=False))
                    if len(results) >= max(1, min(100, int(limit))):
                        return list(results.values())
                except (ValueError, TypeError, PlaywrightError):
                    continue
            if progress:
                progress(dict(found=len(results), scrolls=round_index + 1))
            stalled = stalled + 1 if len(results) == before else 0
            if stalled >= 4:
                break
            self.facebook._scroll_post_feed(self.page)
            self.page.wait_for_timeout(700)
        return list(results.values())

    def connection_root(self):
        root = self.main()
        headings = root.get_by_role('heading', level=1)
        for index in range(headings.count()):
            heading = headings.nth(index)
            if not heading.is_visible():
                continue
            ancestor = heading
            for _ in range(12):
                ancestor = ancestor.locator('xpath=..')
                if not ancestor.count() or ancestor.evaluate('el => el === document.body'):
                    break
                pattern = r'^(?:Tham gia nhóm|Join group|Thêm bạn bè|Kết bạn|Add friend|Đã tham gia|Joined|Hủy yêu cầu|Cancel request|Bạn bè|Friends|Hủy lời mời|Hủy lời mời kết bạn|Cancel friend request)$'
                buttons = ancestor.get_by_role('button', name=re.compile(pattern, re.I))
                visible = [buttons.nth(i) for i in range(buttons.count()) if buttons.nth(i).is_visible()]
                if len(visible) == 1:
                    return ancestor
                if len(visible) > 1:
                    raise OutreachNeedsReview('Có nhiều nút kết nối khác nhau; hãy mở đúng trang cá nhân/nhóm để kiểm tra.')
        raise OutreachNeedsReview('Chưa xác định được phần thông tin và nút kết nối của đúng đối tượng.')

    def connect(self, action, url, cancel=None):
        kind = 'group' if action == 'join_group' else 'person'
        target = normalize_target(kind, url)
        self.open(target, cancel)
        if kind == 'group':
            self.facebook.dismiss_group_welcome(cancel)
        root = self.connection_root()
        existing = self.button(root, r'^(?:Đã tham gia|Joined|Hủy yêu cầu|Cancel request|Bạn bè|Friends|Hủy lời mời|Hủy lời mời kết bạn|Cancel friend request)$')
        if existing is not None:
            return dict(status='skipped', message='Đã kết nối hoặc đã gửi yêu cầu trước đó.')
        pattern = r'^(?:Tham gia nhóm|Join group)$' if kind == 'group' else r'^(?:Thêm bạn bè|Kết bạn|Add friend)$'
        button = self.button(root, pattern)
        if button is None:
            raise OutreachNeedsReview('Không có nút kết nối trên trang đã chọn. Kiểm tra quyền hoặc trạng thái trên Facebook.')
        self.checkpoint(cancel)
        self.mutated = True
        button.click(timeout=4000)
        self.page.wait_for_timeout(700)
        # Do not answer membership questions, accept rules or select an identity automatically.
        dialogs = self.page.get_by_role('dialog')
        if any(dialogs.nth(i).is_visible() for i in range(dialogs.count())):
            raise OutreachNeedsReview('Facebook mở hộp xác nhận/câu hỏi. Hoàn tất trực tiếp trên profile rồi kiểm tra lịch sử.')
        confirmed = self.button(self.connection_root(), r'^(?:Đã tham gia|Joined|Hủy yêu cầu|Cancel request|Hủy lời mời|Hủy lời mời kết bạn|Cancel friend request|Bạn bè|Friends)$')
        if confirmed is None:
            raise OutreachNeedsReview('Đã bấm kết nối nhưng chưa xác nhận được trạng thái. Không tự gửi lại.')
        if re.fullmatch(r'(?:Đã tham gia|Joined|Bạn bè|Friends)', confirmed.inner_text().strip(), re.I):
            return dict(status='done', message='Facebook đã hiển thị trạng thái đã tham gia / bạn bè.')
        return dict(status='pending', message='Đã gửi yêu cầu; cần đối phương hoặc quản trị viên chấp thuận.')

    def send_message(self, target, message, cancel=None):
        url = normalize_target('thread', target)
        if not message.strip():
            raise ValueError('Tin nhắn không được trống.')
        self.open(url, cancel)
        resolved = normalize_target('thread', self.page.url)
        if resolved != url:
            raise OutreachNeedsReview('Facebook mở hội thoại khác với đích đã duyệt; chưa gửi tin.')
        root = self.main()
        editors = root.locator('[contenteditable="true"][role="textbox"]')
        visible = [editors.nth(i) for i in range(editors.count()) if editors.nth(i).is_visible()]
        if len(visible) != 1:
            raise OutreachNeedsReview('Không xác định được duy nhất ô soạn tin của hội thoại đã chọn.')
        editor = visible[0]
        previous = root.get_by_text(message.strip(), exact=True).count()
        self.checkpoint(cancel)
        editor.fill(message.strip(), timeout=4000)
        self.checkpoint(cancel)
        self.mutated = True
        editor.press('Enter')
        self.page.wait_for_timeout(1000)
        if editor.inner_text(timeout=1000).strip() or root.get_by_text(message.strip(), exact=True).count() <= previous:
            raise OutreachNeedsReview('Đã gửi thao tác nhưng chưa thấy tin trong hội thoại. Kiểm tra Messenger; không tự gửi lại.')
        return dict(status='sent', message='Đã thấy tin nhắn trong hội thoại; chưa xác nhận người nhận đã đọc.')

    def _like_article(self, article, cancel):
        pattern = r'^(?:Thích|Like|Bỏ thích|Unlike|Gỡ Thích|Remove Like|Remove reaction|Gỡ cảm xúc)$'
        matches = article.get_by_role('button', name=re.compile(pattern, re.I))
        for index in range(matches.count()):
            button = matches.nth(index)
            if not button.is_visible():
                continue
            # A comment's Like button is not the post's Like button.
            own = button.evaluate('''(el, root) => el.closest('[role=article]') === root''', article.element_handle())
            if not own:
                continue
            unlike = r'(?:Bỏ thích|Unlike|Gỡ Thích|Remove Like|Remove reaction|Gỡ cảm xúc)'
            labels = [button.get_attribute('aria-label') or '', button.inner_text().strip()]
            if button.get_attribute('aria-pressed') == 'true' or any(re.fullmatch(unlike, label, re.I) for label in labels):
                return False
            self.checkpoint(cancel)
            self.mutated = True
            button.click(timeout=3000)
            self.page.wait_for_timeout(500)
            labels = [button.get_attribute('aria-label') or '', button.inner_text().strip()]
            if button.get_attribute('aria-pressed') != 'true' and not any(re.fullmatch(unlike, label, re.I) for label in labels):
                raise OutreachNeedsReview('Chưa xác nhận được trạng thái thích. Kiểm tra bài viết trước khi chạy lại.')
            return True
        return False

    def engage(self, target, cancel=None):
        try:
            url = normalize_target('post', target)
            kind = 'post'
        except ValueError:
            url = normalize_target('person', target)
            kind = 'person'
        self.open(url, cancel)
        accepted_authors = {url}
        if kind == 'person':
            accepted_authors.add(normalize_target('person', self.page.url))
        root = self.main()
        articles = root.locator('[role="article"]')
        for index in range(min(articles.count(), 15)):
            self.checkpoint(cancel)
            article = articles.nth(index)
            if not article.is_visible():
                continue
            if kind == 'person':
                authors = article.locator('h2 a[href], h3 a[href]')
                matched = False
                for i in range(authors.count()):
                    try:
                        author = normalize_target('person', urljoin(url, authors.nth(i).get_attribute('href') or ''))
                        matched = matched or author in accepted_authors
                    except ValueError:
                        continue
                if not matched:
                    continue
            else:
                links = article.locator('a[href*="/posts/"], a[href*="story_fbid="]')
                if not any(post_identity(urljoin(url, links.nth(i).get_attribute('href') or '')) == url for i in range(links.count())):
                    continue
            if self._like_article(article, cancel):
                return dict(status='done', message='Đã thích một bài của đúng đối tượng; bỏ qua bài đã thích.')
        return dict(status='skipped', message='Chưa thấy bài phù hợp chưa thích trong phần đang hiển thị.')

    def perform(self, job, cancel=None):
        action = job['action']
        if action in {'join_group', 'add_friend'}:
            return self.connect(action, job['target'], cancel)
        if action == 'message':
            return self.send_message(job['target'], job['content'], cancel)
        if action == 'engage':
            return self.engage(job['target'], cancel)
        if action == 'group_post':
            self.checkpoint(cancel)
            self.mutated = True
            result = self.facebook.publish_post(job['target'], job['content'], json.loads(job['media_json']), cancel_event=cancel)
            if not result.get('submitted'):
                raise OutreachNeedsReview('Chưa xác nhận được thao tác đăng bài.')
            return dict(status='submitted', message='Đã gửi bài; nhóm có thể vẫn đang chờ quản trị viên duyệt.')
        raise ValueError('Tác vụ chưa được hỗ trợ.')
