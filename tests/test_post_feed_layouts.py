"""Exercise rendered feed variants instead of assuming every post is an article."""
import os
import subprocess
import sys
import textwrap
import unittest


class PostFeedLayoutTests(unittest.TestCase):
    def test_group_layouts_hydration_and_exact_reported_permalink(self):
        script = textwrap.dedent(r"""
            from datetime import datetime
            from types import SimpleNamespace
            from playwright.sync_api import sync_playwright
            from backend.browser.facebook import FacebookBrowser
            from backend.services.comment_rules import scan_keywords
            from backend.facebook.parsers.post_date import VIETNAM_TZ

            url = 'https://www.facebook.com/groups/524659961313411/permalink/2654670161645703/?rdid=NT6QTWCohsabhYcv#'
            group = 'https://www.facebook.com/groups/524659961313411/'
            message = ('Em đang làm nhà bếp chuẩn bị mua thiêt bị bếp . Mấy bác từng trải cho em 1 số trải nghiệm với ạ\n'
                       'Máy rửa chén mua loại nào\nBếp từ loại nào\nHút mùi loại nào ạ .\n'
                       'Và mua của hãng luôn hay mua qua sale hay qua cửa hàng ạ ?\n'
                       'Em đang thiên về Boch vì nghe thấy rì viu khá ổn .')
            stamp = int(datetime.now(VIETNAM_TZ).timestamp())
            with sync_playwright() as pw:
                try:
                    browser = pw.chromium.launch(headless=True)
                except Exception as exc:
                    if 'Executable doesn' in str(exc): raise SystemExit(77)
                    raise
                context = browser.new_context()
                context.add_cookies([dict(name='c_user', value='123', domain='.facebook.com', path='/')])
                html = ''
                context.route('**/*', lambda route: route.fulfill(status=200, content_type='text/html; charset=utf-8', body=html))
                page = context.new_page()
                facebook = FacebookBrowser(SimpleNamespace(page=page, context=context))
                header = f'<h3><a href="{url}"><span aria-label="Vừa xong">Thời gian</span></a></h3>'
                for wrapper, attribute, tag in [
                    ('<div role="article">', 'data-ad-preview="message"', 'div'),
                    ('<div data-pagelet="FeedUnit_42">', 'data-ad-comet-preview="message"', 'span'),
                    ('<div role="feed"><div>', 'data-ad-rendering-role="story_message"', 'div'),
                    ('<div role="feed"><div>', 'data-ad-preview="message"', 'span'),
                    ('<div>', 'data-ad-rendering-role="story_message"', 'div'),
                ]:
                    html = wrapper + header + f'<{tag} {attribute}>{message}</{tag}>' + '</div>'
                    if 'role="feed"' in wrapper: html += '</div>'
                    posts = facebook.find_buying_posts(group, scan_keywords(), group_only=True, scroll_count=1)
                    assert [p['id'] for p in posts] == ['2654670161645703'], (wrapper, posts, facebook.last_post_scan_stats)
                    assert ' '.join(posts[0]['message'].split()) == ' '.join(message.split()), posts[0]['message']
                    assert posts[0]['url'].endswith('/permalink/2654670161645703/')

                # Post content is initially folded; its question is only available after See more.
                html = f'''<div role="feed"><div>{header}<div data-ad-rendering-role="story_message">
                    <span>Em đang làm nhà...</span><button onclick="this.parentElement.innerText='Máy rửa chén mua loại nào, bếp từ loại nào ạ?'">Xem thêm</button>
                    </div></div></div>'''
                posts = facebook.find_buying_posts(group, scan_keywords(), group_only=True, scroll_count=1)
                assert len(posts) == 1 and 'bếp từ loại nào' in posts[0]['message'], posts

                # The timestamp's URL can be absent until the pointer reaches it.
                html = (f'<div><h3><a href="#" aria-label="Vừa xong" onmouseover="this.href=\'{url}\'">Vừa xong</a></h3>'
                        f'<div data-ad-rendering-role="story_message">{message}</div></div>')
                posts = facebook.find_buying_posts(group, scan_keywords(), group_only=True, scroll_count=1)
                assert [p['id'] for p in posts] == ['2654670161645703'], posts

                # These alternate timestamp links must still identify the right group/post.
                for href in [
                    group + '?multi_permalinks=2654670161645703&ref=share',
                    'https://www.facebook.com/permalink.php?story_fbid=2654670161645703&id=524659961313411',
                ]:
                    html = f'<div role="feed"><div><a href="{href}" data-utime="{stamp}">Vừa xong</a><div data-ad-rendering-role="story_message">{message}</div></div></div>'
                    posts = facebook.find_buying_posts(group, scan_keywords(), group_only=True, scroll_count=1)
                    assert [p['id'] for p in posts] == ['2654670161645703'], (href, posts)

                # A buyer comment must not become the post body when the original is absent.
                html = f'<div role="feed"><div>{header}<div role="article"><a href="{url.split("?")[0]}?comment_id=99">Khách</a><div dir="auto">{message}</div></div></div></div>'
                assert facebook.find_buying_posts(group, scan_keywords(), group_only=True, scroll_count=1) == []
                assert facebook.last_post_scan_stats['skipped_no_body'] == 1

                # No message marker: read only text between the header and actions.
                # A buyer question below the action row cannot affect the author.
                for post_text, expected in [(message, 1), ('Ảnh nhà bếp mình vừa hoàn thiện', 0)]:
                    html = (f'<div role="feed"><div>{header}<div dir="auto">{post_text}</div>'
                            '<button>Thích</button><button>Bình luận</button>'
                            f'<div role="article"><div dir="auto">{message}</div><a href="{url.split("?")[0]}?comment_id=99">Khách</a></div>'
                            '</div></div>')
                    posts = facebook.find_buying_posts(group, scan_keywords(), group_only=True, scroll_count=1)
                    assert len(posts) == expected, (post_text, posts)

                # domcontentloaded is earlier than the asynchronously rendered feed.
                delayed = f'<div>{header}<div data-ad-rendering-role="story_message">{message}</div></div>'
                import json
                html = '<div role="feed" id="feed"></div><script>setTimeout(()=>document.getElementById("feed").innerHTML=' + json.dumps(delayed) + ',1800)</script>'
                posts = facebook.find_buying_posts(group, scan_keywords(), group_only=True, scroll_count=1)
                assert len(posts) == 1, (posts, facebook.last_post_scan_stats)

                # Visible cards with unrecognized links must fail with a diagnosis.
                html = '<div role="feed"><div><a href="/groups/524659961313411/">Tên nhóm</a><div data-ad-rendering-role="story_message">Xin review mrb</div></div></div>'
                try:
                    facebook.find_buying_posts(group, scan_keywords(), group_only=True, scroll_count=1)
                    raise AssertionError('Unreadable feed must not be reported as zero customers')
                except RuntimeError as exc:
                    assert 'Không trích xuất được link bài' in str(exc), str(exc)
                assert facebook.last_post_scan_stats['reason'] == 'feed_unreadable'
                browser.close()
        """)
        result = subprocess.run(
            [sys.executable, '-c', script], capture_output=True, text=True, encoding='utf-8',
            env=dict(os.environ, PYTHONIOENCODING='utf-8'), timeout=90,
        )
        if result.returncode == 77:
            self.skipTest('Playwright Chromium is not installed')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
