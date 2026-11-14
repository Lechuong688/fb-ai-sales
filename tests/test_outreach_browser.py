"""Intercept all browser traffic; exercise actions on local DOM fixtures only."""
import os
import subprocess
import sys
import textwrap
import unittest


class OutreachBrowserTests(unittest.TestCase):
    def test_discovery_connections_messages_and_reactions_use_exact_targets(self):
        script = textwrap.dedent(r"""
            from types import SimpleNamespace
            import threading
            from playwright.sync_api import sync_playwright
            from backend.browser.facebook import FacebookBrowser
            from backend.browser.outreach import OutreachBrowser, OutreachNeedsReview

            with sync_playwright() as pw:
                try:
                    browser = pw.chromium.launch(headless=True)
                except Exception as exc:
                    if 'Executable doesn' in str(exc): raise SystemExit(77)
                    raise
                context = browser.new_context()
                context.add_cookies([dict(name='c_user', value='123', domain='.facebook.com', path='/')])
                fixture = {'html': '<main></main>'}
                context.route('**/*', lambda route: route.fulfill(status=200, content_type='text/html; charset=utf-8', body=fixture['html']))
                page = context.new_page()
                facebook = FacebookBrowser(SimpleNamespace(page=page, context=context))
                adapter = OutreachBrowser(facebook)

                fixture['html'] = '''<main><a href="/groups/feed/">Navigation</a><div role="article"><h2><a href="/groups/123/?ref=share">Gia dụng Hà Nội</a></h2><p>Nhóm khách gia đình Hà Nội</p><a href="/groups/123/">Xem nhóm</a></div></main>'''
                results = adapter.discover('group', 'bếp', 'Gia dụng', 'Hà Nội', limit=1)
                assert len(results) == 1 and results[0]['name'] == 'Gia dụng Hà Nội', results
                assert results[0]['url'] == 'https://www.facebook.com/groups/123/'
                assert results[0]['industry'] == 'Gia dụng' and results[0]['region'] == 'Hà Nội'
                assert 'search/groups' in page.url
                fixture['html'] = '''<main><a href="/messages/">Messages</a><div role="article"><h2><a href="/profile.php?id=456&amp;ref=search">Lan</a></h2><p>Nội thất Hà Nội</p></div></main>'''
                results = adapter.discover('person', 'Lan', 'Nội thất', 'Hà Nội', limit=1)
                assert results[0]['url'] == 'https://www.facebook.com/profile.php?id=456', results

                fixture['html'] = '''<main><section><h1>Lan</h1><button onclick="window.connected='456';this.innerText='Cancel friend request'">Add friend</button></section><div role="article"><h2>Other person</h2><button onclick="window.wrong=true">Add friend</button></div></main>'''
                result = adapter.connect('add_friend', 'https://facebook.com/profile.php?id=456')
                assert result['status'] == 'pending' and page.evaluate('window.connected') == '456'
                assert not page.evaluate('Boolean(window.wrong)')
                fixture['html'] = '<main><section><h1>Lan</h1><button onclick="window.wrong=true">Cancel friend request</button></section></main>'
                result = adapter.connect('add_friend', 'https://facebook.com/456/')
                assert result['status'] == 'skipped' and not page.evaluate('Boolean(window.wrong)')

                fixture['html'] = '''<main><section><h1>Gia dụng</h1><button onclick="this.innerText='Đã tham gia'">Tham gia nhóm</button></section></main>'''
                assert adapter.connect('join_group', 'https://facebook.com/groups/123/')['status'] == 'done'
                fixture['html'] = '''<main><section><h1>Gia dụng</h1><button onclick="document.getElementById('questions').style.display='block'">Tham gia nhóm</button></section></main><div id="questions" role="dialog" style="display:none"><input placeholder="Câu hỏi thành viên"><button onclick="window.wrong=true">Gửi</button></div>'''
                try:
                    adapter.connect('join_group', 'https://facebook.com/groups/123/')
                    raise AssertionError('Membership questions require manual completion')
                except OutreachNeedsReview:
                    assert page.get_by_role('dialog').is_visible()
                    assert not page.evaluate('Boolean(window.wrong)')

                fixture['html'] = '''<main><h1>Hội thoại Lan</h1><div id="messages"></div><div contenteditable="true" role="textbox" onkeydown="if(event.key==='Enter'){event.preventDefault();const bubble=document.createElement('div');bubble.textContent=this.innerText;document.getElementById('messages').append(bubble);this.innerText='';}"></div></main>'''
                result = adapter.send_message('https://facebook.com/messages/e2ee/t/123/', 'Chào Lan, nội dung đã duyệt')
                assert result['status'] == 'sent'
                assert page.locator('#messages').inner_text() == 'Chào Lan, nội dung đã duyệt'
                fixture['html'] = '''<script>history.replaceState({}, '', '/messages/t/999/')</script><main><div role="textbox" contenteditable="true"></div></main>'''
                adapter = OutreachBrowser(facebook)
                try:
                    adapter.send_message('https://facebook.com/messages/t/123/', 'Must not send')
                    raise AssertionError('Wrong thread must not be used')
                except OutreachNeedsReview:
                    assert not adapter.mutated

                fixture['html'] = '''<main><div role="article"><h2><a href="/456/">Lan</a></h2><a href="/456/posts/42/">Vừa xong</a><button id="like" aria-pressed="false" onclick="this.innerText='Unlike';this.setAttribute('aria-pressed','true');window.liked=true">Like</button><div role="article"><button onclick="window.wrong=true">Unlike</button></div></div></main>'''
                result = adapter.engage('https://facebook.com/456/')
                assert result['status'] == 'done' and page.evaluate('window.liked')
                assert not page.evaluate('Boolean(window.wrong)')
                fixture['html'] = '''<main><div role="article"><a href="/456/posts/42/">Vừa xong</a><button aria-pressed="true" onclick="window.wrong=true">Unlike</button></div></main>'''
                result = adapter.engage('https://facebook.com/456/posts/42/')
                assert result['status'] == 'skipped' and not page.evaluate('Boolean(window.wrong)')
                stop = threading.Event(); stop.set()
                previous = page.url
                try:
                    adapter.send_message('https://facebook.com/messages/t/123/', 'Cancelled', stop)
                    raise AssertionError('Cancelled action must not start')
                except InterruptedError:
                    assert page.url == previous
                browser.close()
        """)
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True,
                                encoding='utf-8', env=dict(os.environ, PYTHONIOENCODING='utf-8'), timeout=60)
        if result.returncode == 77:
            self.skipTest('Playwright Chromium is not installed')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
