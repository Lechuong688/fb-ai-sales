"""Real DOM fixtures: no Facebook requests or real publishing."""
import os
import subprocess
import sys
import textwrap
import unittest


class GroupWelcomeTests(unittest.TestCase):
    def test_welcome_is_closed_and_scan_and_publish_continue(self):
        script = textwrap.dedent(r'''
            import threading
            from pathlib import Path
            from types import SimpleNamespace
            from datetime import datetime
            from playwright.sync_api import sync_playwright
            from backend.browser.facebook import FacebookBrowser
            from backend.facebook.parsers.post_date import VIETNAM_TZ

            def card(text, label='Đóng', extra='', close=True):
                button = f'<button aria-label="{label}" onclick="this.closest(\'[role=dialog]\').remove()">X</button>' if close else ''
                return f'<div role="dialog" style="position:fixed;inset:0;background:white;z-index:99">{button}<h2>{text}</h2>{extra}<button onclick="window.continued=true">Tiếp tục</button></div>'

            with sync_playwright() as pw:
                if not Path(pw.chromium.executable_path).is_file():
                    raise SystemExit(77)
                browser = pw.chromium.launch(headless=True)
                context = browser.new_context()
                context.add_cookies([dict(name='c_user', value='123', domain='.facebook.com', path='/')])
                fixture = {'html': '<body></body>'}
                context.route('**/*', lambda route: route.fulfill(status=200, content_type='text/html; charset=utf-8', body=fixture['html']))
                page = context.new_page()
                page.goto('https://www.facebook.com/groups/demo/')
                facebook = FacebookBrowser(SimpleNamespace(page=page, context=context))

                for greeting, label in [
                    ('Bếp ơi, chào mừng bạn đến với Cộng Đồng Sử Dụng Máy Rửa Bát Bosch!', 'Đóng'),
                    ('Welcome to our kitchen community!', 'Close'),
                ]:
                    page.set_content(card(greeting, label))
                    assert facebook.dismiss_group_welcome() == 1
                    assert page.locator('[role=dialog]').count() == 0
                    assert not page.evaluate('Boolean(window.continued)')

                for html in [
                    card('Xác minh danh tính để tiếp tục'),
                    card('Tạo bài viết', extra='<div role="textbox" contenteditable="true">Chào mừng bạn đến với nhóm</div>'),
                    card('Chào mừng bạn đến với nhóm', extra='<input type="password">'),
                    card('Chào mừng bạn đến với nhóm', close=False),
                ]:
                    page.set_content(html)
                    assert facebook.dismiss_group_welcome() == 0
                    assert page.locator('[role=dialog]').is_visible()
                    assert not page.evaluate('Boolean(window.continued)')

                page.set_content(card('Chào mừng bạn đến với nhóm'))
                stop = threading.Event()
                stop.set()
                assert facebook.dismiss_group_welcome(stop) == 0
                assert page.locator('[role=dialog]').is_visible()

                stamp = int(datetime.now(VIETNAM_TZ).timestamp())
                fixture['html'] = card('Bếp ơi, chào mừng bạn đến với Cộng Đồng Sử Dụng Máy Rửa Bát Bosch!') + f'<div role="article"><h2><a href="/user/demo">Khách</a></h2><a href="/groups/demo/posts/42/" data-utime="{stamp}">Vừa xong</a><div data-ad-preview="message">Cần mua máy rửa bát</div></div>'
                posts = facebook.find_buying_posts('https://www.facebook.com/groups/demo/', ['cần mua'], group_only=True, scroll_count=1)
                assert [post['id'] for post in posts] == ['42'], posts
                assert page.locator('[role=dialog]').count() == 0

                fixture['html'] = card('Chào mừng bạn đến với nhóm') + """<button onclick="document.getElementById('composer').style.display='block'">Tạo bài viết</button>
                    <div role="dialog" id="composer" style="display:none"><div contenteditable="true" role="textbox"></div><button onclick="window.submitted=true">Đăng</button></div>"""
                result = facebook.publish_post('https://www.facebook.com/groups/demo/', 'Nội dung fixture')
                assert result['submitted'] and page.evaluate('window.submitted === true')
                assert page.locator('#composer').is_visible()
                assert not page.evaluate('Boolean(window.continued)')
                browser.close()
                print('Welcome dismissal, protected dialogs, cancellation, scanning and fixture publishing passed.')
        ''')
        result = subprocess.run(
            [sys.executable, '-X', 'faulthandler', '-c', script], capture_output=True,
            text=True, encoding='utf-8', env=dict(os.environ, PYTHONIOENCODING='utf-8'), timeout=40,
        )
        if result.returncode == 77:
            self.skipTest('Playwright Chromium is not installed')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
