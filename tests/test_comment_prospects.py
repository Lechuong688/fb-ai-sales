"""Comment acquisition and reply targeting, using local fixtures only."""
import os
import subprocess
import sys
import textwrap
import unittest
from types import SimpleNamespace
from datetime import datetime, timedelta
from unittest.mock import patch

from backend.services.comment_rules import preview_comments, suggest_target, scan_keywords, is_customer_post, post_identity
from tests.test_product_catalog import fixture_catalog
from tests.test_leads import buyer_post
from tests.test_buyer_post_scan import FakeArticle, FakeBrowser, FakePage
from backend.browser.facebook import FacebookBrowser
from backend.workers.browser_worker import BrowserWorker
from backend.facebook.parsers.post_date import VIETNAM_TZ


def comment(number, text='Xin giá với', parent='Bên em bán bếp từ'):
    return dict(buyer_post(), url=f'https://www.facebook.com/groups/100/posts/1/?comment_id={number}',
                message=text, parent_message=parent, target_type='comment', author=f'Khách {number}')


class CommentProspectTests(unittest.TestCase):
    def test_empty_scan_reports_unreadable_and_irrelevant_posts(self):
        from tests.test_buyer_post_scan import FakeLocator

        class MissingBody(FakeArticle):
            def locator(self, selector):
                if selector == 'div[data-ad-preview="message"]':
                    return FakeLocator()
                return super().locator(selector)

        class BrokenBody(FakeArticle):
            def locator(self, selector):
                if selector == 'div[data-ad-preview="message"]':
                    raise RuntimeError('Fixture: nội dung không đọc được')
                return super().locator(selector)

        page = FakePage([
            MissingBody('Xin review mrb', 'https://facebook.com/groups/demo/posts/1/'),
            FakeArticle('Bếp từ sẵn kho, inbox báo giá', 'https://facebook.com/groups/demo/posts/2/'),
            BrokenBody('Xin review mrb', 'https://facebook.com/groups/demo/posts/3/'),
        ])
        facebook = FacebookBrowser(FakeBrowser(page))
        self.assertEqual(facebook.find_buying_posts('https://facebook.com/groups/demo/', scan_keywords(),
                                                    scroll_count=2, group_only=True), [])
        stats = facebook.last_post_scan_stats
        self.assertEqual(stats['seen_posts'], 3)
        self.assertEqual(stats['skipped_no_body'], 1)
        self.assertEqual(stats['skipped_irrelevant'], 1)
        self.assertEqual(stats['extraction_errors'], 2)
        self.assertIn('Fixture', stats['last_extraction_error'])

    def test_review_and_kitchen_purchase_examples_survive_the_full_scan(self):
        examples = [
            '**E xin review mrb bosh và eurusun với ạ**',
            'Em đang làm nhà bếp chuẩn bị mua thiêt bị bếp. Mấy bác từng trải cho em 1 số trải nghiệm với ạ\n'
            'Máy rửa chén mua loại nào\nBếp từ loại nào\nHút mùi loại nào ạ.\n'
            'Và mua của hãng luôn hay mua qua sale hay qua cửa hàng ạ?\n'
            'Em đang thiên về Boch vì nghe thấy rì viu khá ổn.',
            'Bếp từ loại nào ạ?',
            'E xin review mrc với ạ',
        ]
        for catalog in (None, fixture_catalog()):
            for message in examples:
                with self.subTest(message=message, catalog=bool(catalog)):
                    self.assertTrue(is_customer_post(message, catalog=catalog))
                    page = FakePage([FakeArticle(message, 'https://facebook.com/groups/demo/posts/42/')])
                    facebook = FacebookBrowser(FakeBrowser(page))
                    found = facebook.find_buying_posts('https://facebook.com/groups/demo/', scan_keywords(),
                                                       catalog=catalog, group_only=True, scroll_count=1)
                    self.assertEqual([post['id'] for post in found], ['42'])
                    draft = suggest_target(found[0], catalog=catalog)
                    self.assertEqual(draft['rule_id'], 'advice')
                    self.assertTrue(draft['comment'])
        for message in ('Em bán mrb bosh, inbox báo giá', 'Mrb bosh sẵn kho, xin review từ khách',
                        'Xin review quán ăn', 'Đã mua rồi, xin review mrb'):
            self.assertFalse(is_customer_post(message))

    def test_reviewed_post_comments_send_exact_drafts_and_skip_sent_posts(self):
        worker = BrowserWorker()
        worker.profile_name = 'demo'
        post = dict(buyer_post(), draft_comment='Bác cho em xin ngân sách dự kiến ạ.')
        with patch('backend.workers.browser_worker.browser_pool') as pool, \
             patch('backend.workers.browser_worker.CommentHistoryService') as history, \
             patch('backend.workers.browser_worker.signals'), \
             patch('backend.workers.browser_worker.AppLogger'), \
             patch('backend.workers.browser_worker._ScanCancellation.wait'):
            pool.get_session.return_value = SimpleNamespace(running=True, logged_in=True)
            worker.comment_on_selected_posts(dict(posts=[post]))
            worker.comment_on_selected_posts(dict(posts=[comment(1)], reviewed=True))
            pool.get.assert_not_called()
            history.return_value.was_sent.side_effect = [False, True]
            worker.comment_on_selected_posts(dict(posts=[post], reviewed=True))
            worker.comment_on_selected_posts(dict(posts=[post], reviewed=True))
            pool.get.return_value.facebook.comment_on_post.assert_called_once_with(post_identity(post['url']), post['draft_comment'])
            history.return_value.record.assert_called_once_with('demo', post_identity(post['url']), post['draft_comment'], 'sent')

    def test_short_question_uses_product_but_not_seller_exclusions_from_parent(self):
        result = suggest_target(comment(1))
        self.assertEqual(result['rule_id'], 'price')
        self.assertEqual(result['product'], 'bếp từ')
        shorthand = suggest_target(comment(1, parent='E xin review mrb bosh và eurusun với ạ'))
        self.assertEqual(shorthand['product'], 'máy rửa bát')
        self.assertEqual(shorthand['rule_id'], 'price')
        for text in ['Bên em bán giá tốt', 'Đã mua rồi', 'Đẹp quá', 'Không cần mua nữa']:
            self.assertEqual(suggest_target(comment(2, text))['status'], 'skipped')
        self.assertEqual(suggest_target(comment(2, parent='Ảnh phong cảnh'))['status'], 'skipped')
        self.assertEqual(suggest_target(comment(2), products=[])['status'], 'skipped')
        self.assertEqual(suggest_target(comment(2, parent='Bếp từ và máy rửa bát'))['status'], 'manual_review')

    def test_reviewed_reply_worker_sends_each_draft_and_skips_sent_targets(self):
        worker = BrowserWorker()
        worker.profile_name = 'demo'
        posts = [dict(comment(1), draft_comment='Trả lời riêng một'), dict(comment(2), draft_comment='Trả lời riêng hai')]
        with patch('backend.workers.browser_worker.browser_pool') as pool, \
             patch('backend.workers.browser_worker.CommentHistoryService') as history, \
             patch('backend.workers.browser_worker.signals') as events, \
             patch('backend.workers.browser_worker.AppLogger'), \
             patch('backend.workers.browser_worker._ScanCancellation.wait'):
            pool.get_session.return_value = SimpleNamespace(running=True, logged_in=True)
            worker.reply_to_selected_comments(dict(posts=posts))
            pool.get.assert_not_called()
            worker.reply_to_selected_comments(dict(posts=[dict(posts[0], url='https://facebook.com/groups/100/posts/1/')], reviewed=True))
            pool.get.assert_not_called()
            history.return_value.was_sent.side_effect = [False, True]
            worker.reply_to_selected_comments(dict(posts=posts, reviewed=True))
            pool.get.return_value.facebook.comment_on_post.assert_called_once_with(posts[0]['url'], posts[0]['draft_comment'])
            history.return_value.record.assert_called_once_with('demo', posts[0]['url'], posts[0]['draft_comment'], 'sent')
            self.assertTrue(events.comment_result.emit.call_args.args[1]['skipped'])
            self.assertFalse(worker.operation_active)

    def test_reply_review_ui_only_sends_reviewed_comment_targets(self):
        script = textwrap.dedent('''
            import tempfile
            from pathlib import Path
            from types import SimpleNamespace
            from unittest.mock import Mock, patch
            from PySide6.QtWidgets import QApplication, QDialog
            from PySide6.QtCore import Qt
            from backend.services.comment_rules import CommentRuleStore
            from frontend.pages.comment_page import CommentPage
            app = QApplication([])
            worker = Mock(operation_active=False)
            with tempfile.TemporaryDirectory() as directory, patch('frontend.pages.comment_page.AccountService') as accounts, patch('frontend.pages.comment_page.GroupService'), patch('frontend.pages.comment_page.load_company_catalog', return_value=None), patch('frontend.pages.comment_page.CommentRuleStore', return_value=CommentRuleStore(Path(directory)/'rules.json')), patch('frontend.pages.comment_page.browser_pool') as pool:
                accounts.return_value.get_all.return_value = []
                pool.get_worker.return_value = worker
                pool.get_session.return_value = SimpleNamespace(running=True, logged_in=True)
                page = CommentPage()
                assert page.min_ad_comments_input.value() == 10
                page.scan_comments_checkbox.setChecked(False)
                assert not page.min_ad_comments_input.isEnabled()
                page.scan_comments_checkbox.setChecked(True)
                assert page.min_ad_comments_input.isEnabled()
                page._pending_profile = 'demo'
                post = dict(url='https://www.facebook.com/groups/100/posts/1/?comment_id=7', message='Xin giá', parent_message='Bên em bán bếp từ', target_type='comment', author='Khách')
                page._show_posts('demo', [post])
                page.results.item(0, 0).setCheckState(Qt.Checked)
                page.results.item(0, 6).setText('Nội dung đã sửa')
                assert page.reply_comments_button.isEnabled()
                with patch('frontend.pages.comment_page.QDialog.exec', return_value=QDialog.Rejected):
                    page.reply_selected_comments()
                worker.comment_replies_requested.emit.assert_not_called()
                with patch('frontend.pages.comment_page.QDialog.exec', return_value=QDialog.Accepted):
                    page.reply_selected_comments()
                request = worker.comment_replies_requested.emit.call_args.args[0]
                assert request['reviewed'] is True
                assert request['posts'][0]['draft_comment'] == 'Nội dung đã sửa'
                assert request['posts'][0]['url'] == post['url']
                assert page._scan_active and not page.reply_comments_button.isEnabled()
                page._show_comment_result('demo', dict(url=post['url'], success=True, message='Đã gửi'))
                page._task_status('demo', 'comment', False)
                assert not page.reply_comments_button.isEnabled()
                assert page.results.item(0, 0).checkState() == Qt.Unchecked
                post = dict(url='https://www.facebook.com/groups/100/posts/2/', message='E xin review mrb bosh với ạ', author='Khách')
                page._show_posts('demo', [post])
                page.results.item(0, 0).setCheckState(Qt.Checked)
                assert page.post_comments_button.isEnabled()
                assert not page.reply_comments_button.isEnabled()
                page.comment_input.setPlainText('Nội dung có sẵn')
                with patch('frontend.pages.comment_page.QDialog.exec', return_value=QDialog.Rejected):
                    page.comment_selected_posts()
                worker.post_comments_requested.emit.assert_not_called()
                with patch('frontend.pages.comment_page.QDialog.exec', return_value=QDialog.Accepted):
                    page.comment_selected_posts()
                request = worker.post_comments_requested.emit.call_args.args[0]
                assert request['reviewed'] is True
                assert request['posts'][0]['draft_comment'] == 'Nội dung có sẵn'
                assert request['posts'][0]['url'] == post['url']
                page._show_comment_result('demo', dict(url=post['url'], success=True, message='Đã gửi'))
                page._task_status('demo', 'comment', False)
                assert not page.post_comments_button.isEnabled()
                page.close()
        ''')
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True,
                                encoding='utf-8', env=dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONIOENCODING='utf-8'), timeout=25)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_different_commenters_and_replies_are_distinct(self):
        targets = [comment(1), comment(2), comment(1),
                   dict(comment(1), url=comment(1)['url'] + '&reply_comment_id=3')]
        self.assertEqual([x['status'] for x in preview_comments(targets)],
                         ['draft', 'draft', 'duplicate', 'draft'])

    def test_customer_threads_first_then_popular_relevant_ads_only(self):
        class Labels:
            def __init__(self, text): self.text = text
            def all_inner_texts(self): return [self.text]
        class EngagedArticle(FakeArticle):
            def __init__(self, number, label, text='Bên em bán bếp từ', age=0):
                published = str(int((datetime.now(VIETNAM_TZ) - timedelta(days=age)).timestamp()))
                super().__init__(text, f'https://www.facebook.com/groups/demo/posts/{number}/', published=published)
                self.label = label
            def locator(self, selector):
                if selector == '[role="button"], button, a': return Labels(self.label)
                return super().locator(selector)
        page = FakePage([EngagedArticle(1, '3 bình luận'),
                         EngagedArticle(2, '1,2K bình luận', 'Bếp từ sẵn kho, ai cần mua inbox báo giá'),
                         EngagedArticle(3, '1,2K bình luận', 'Xin tư vấn nên mua bếp từ hãng nào?', age=3),
                         EngagedArticle(4, '99 bình luận', 'Bán điện thoại'),
                         EngagedArticle(5, '3 bình luận', 'Mình cần mua bếp từ cho gia đình'),
                         EngagedArticle(6, '0 bình luận', 'Ai bán bếp từ không?'),
                         EngagedArticle(7, '10 bình luận', 'Bên em bán bếp từ', age=1),
                         EngagedArticle(8, '9 bình luận', 'Bên em bán bếp từ'),
                         EngagedArticle(9, '100 bình luận', 'Bên em bán bếp từ', age=16),
                         EngagedArticle(10, '100 lượt thích', 'Bên em bán bếp từ')])
        facebook = FacebookBrowser(FakeBrowser(page))
        with patch.object(facebook, 'find_comment_buyers', return_value=[]) as read:
            result = facebook.find_buying_posts('https://facebook.com/groups/demo/', ['cần mua', 'tư vấn', 'ai bán'],
                                               scroll_count=1, include_comments=True)
        self.assertEqual({post['id'] for post in result}, {'3', '5', '6'})
        self.assertEqual([call.args[0]['id'] for call in read.call_args_list], ['5', '3', '2', '7'])
        self.assertTrue(all(call.args[0]['source_is_ad'] for call in read.call_args_list[2:]))

    def test_ad_threshold_controls_reading_and_only_customer_comments_are_returned(self):
        class EngagedArticle(FakeArticle):
            def locator(self, selector):
                if selector == '[role="button"], button, a':
                    return SimpleNamespace(all_inner_texts=lambda: ['10 bình luận'])
                return super().locator(selector)
        ad = EngagedArticle('Bên em bán bếp từ, inbox báo giá', 'https://facebook.com/groups/demo/posts/1/')
        buyer = comment(7, 'Xin giá với')
        facebook = FacebookBrowser(FakeBrowser(FakePage([ad])))
        with patch.object(facebook, 'find_comment_buyers', return_value=[buyer]) as read:
            for options in (dict(include_comments=False), dict(include_comments=True, min_ad_comments=11)):
                self.assertEqual(facebook.find_buying_posts('https://facebook.com/groups/demo/', ['cần mua'],
                                                          scroll_count=1, **options), [])
            read.assert_not_called()
            found = facebook.find_buying_posts('https://facebook.com/groups/demo/', ['cần mua'],
                                              scroll_count=1, include_comments=True, min_ad_comments=10)
            self.assertEqual(found, [buyer])
            self.assertEqual(read.call_count, 1)
            self.assertTrue(read.call_args.args[0]['source_is_ad'])

        # Ads must leave more feed-search time so a later customer is not lost
        # to the 55% reservation intended for customer inquiry threads.
        page = FakePage([ad, FakeArticle('Mình cần mua bếp từ', 'https://facebook.com/groups/demo/posts/42/')])
        facebook = FacebookBrowser(FakeBrowser(page))
        with patch('backend.browser.facebook.time.monotonic', side_effect=[0, 0, 0] + [100] * 50):
            found = facebook.find_buying_posts('https://facebook.com/groups/demo/', ['cần mua'],
                                              max_posts=1, scroll_count=1, include_comments=True, max_seconds=180)
        self.assertEqual([post['id'] for post in found], ['42'])

    def test_customer_advice_does_not_require_duplicate_acquisition_keywords(self):
        page = FakePage([FakeArticle('E xin review mrb bosh với ạ', 'https://facebook.com/groups/demo/posts/42/')])
        facebook = FacebookBrowser(FakeBrowser(page))
        found = facebook.find_buying_posts('https://facebook.com/groups/demo/', ['cần mua'], scroll_count=1)
        self.assertEqual([post['id'] for post in found], ['42'])

    def test_real_dom_reads_comments_and_replies_to_exact_target(self):
        script = textwrap.dedent(r"""
            from datetime import datetime
            from types import SimpleNamespace
            from playwright.sync_api import sync_playwright
            from backend.browser.facebook import FacebookBrowser
            from backend.facebook.parsers.post_date import VIETNAM_TZ
            import threading
            with sync_playwright() as pw:
                try:
                    browser = pw.chromium.launch(headless=True)
                except Exception as exc:
                    if 'Executable doesn' in str(exc): raise SystemExit(77)
                    raise
                context = browser.new_context()
                context.add_cookies([dict(name='c_user', value='123', domain='.facebook.com', path='/')])
                stamp = int(datetime.now(VIETNAM_TZ).timestamp())
                source_url = 'https://www.facebook.com/groups/demo/posts/42/'
                def row(number, text, date=None, nested=''):
                    return f'''<div role="article" id="c{number}"><a role="link" href="/user/{number}">Khách {number}</a>
                    <div dir="auto">{text}</div><a href="{source_url}?comment_id={number}" data-utime="{date or stamp}">Vừa xong</a>
                    <button onclick="this.parentElement.querySelector('[role=textbox]').style.display='block'">Trả lời</button>
                    <div role="textbox" contenteditable="true" style="display:none" onkeydown="if(event.key==='Enter'){{event.preventDefault(); window.sent=(window.sent||[]).concat('{number}');this.innerText='';}}"></div>{nested}</div>'''
                html = ('<div role="article"><div data-ad-preview="message">Bên em bán bếp từ</div>'
                        f'<a href="{source_url}" data-utime="{stamp}">Bài gốc</a><button>10 bình luận</button>'
                        '<div id="post-editor" role="textbox" contenteditable="true" onkeydown="if(event.key===\'Enter\'){event.preventDefault();window.postSent=this.innerText;this.innerText=\'\';}"></div>'
                        + row(1, 'Xin giá với', nested=row(2, 'Bên em bán giá tốt'))
                        + row(3, 'Mình cần mua bếp từ') + row(4, 'Đẹp quá')
                        + row(5, 'Xin giá', date=stamp-20*86400) + '</div>'
                        '<div role="article"><a href="/groups/demo/posts/999/">Bài khác</a>'
                        '<div data-ad-preview="message">Bếp từ bài đề xuất</div>'
                        '<div role="textbox" contenteditable="true" onkeydown="window.wrongTarget=true"></div></div>')
                context.route('**/*', lambda route: route.fulfill(status=200, content_type='text/html; charset=utf-8', body=html))
                page = context.new_page()
                facebook = FacebookBrowser(SimpleNamespace(page=page, context=context))
                comment_html = html
                for label, activity, newest in [('Phù hợp nhất', 'Hoạt động mới đây', 'Bài viết mới'), ('Most relevant', 'Recent activity', 'New posts')]:
                    html = f'''<button id="sort" onclick="document.getElementById('sort-menu').style.display='block'">{label}</button>
                    <div id="sort-menu" role="menu" style="display:none">
                      <div role="menuitem" onclick="window.order='activity'"><span>{activity}</span><small>Comment activity</small></div>
                      <div role="menuitem" onclick="window.order='new';document.getElementById('sort').innerText='{newest}';document.getElementById('sort-menu').remove()"><span>{newest}</span><small>Show newest posts first</small></div>
                    </div>
                    <div role="article"><a href="/groups/demo/posts/40/" data-utime="{stamp}">Vừa xong</a><div data-ad-preview="message">Bếp từ sẵn kho, tư vấn miễn phí, inbox báo giá</div></div>
                    <div role="article"><a href="/groups/demo/posts/42/" data-utime="{stamp}">Vừa xong</a><div data-ad-preview="message">Xin tư vấn nên mua bếp từ loại nào?</div></div>'''
                    found = facebook.find_buying_posts('https://www.facebook.com/groups/demo/', ['tư vấn', 'báo giá'], group_only=True, scroll_count=1)
                    assert page.evaluate('window.order') == 'new'
                    assert facebook.last_post_scan_stats['feed_sort'] == 'new_posts'
                    assert [post['id'] for post in found] == ['42'], found
                page.set_content('<button onclick="document.getElementById(\'menu\').style.display=\'block\'">Phù hợp nhất</button><div id="menu" style="display:none">Hoạt động mới đây</div>')
                try:
                    facebook._select_new_posts(page)
                    raise AssertionError('Must not scan the wrong feed order')
                except RuntimeError:
                    pass
                html = comment_html
                leads = facebook.find_buying_posts('https://www.facebook.com/groups/demo/', ['cần mua'],
                                                   group_only=True, scroll_count=1, include_comments=True)
                assert {lead['id'] for lead in leads} == {'1', '3'}, leads
                assert all(lead['target_type'] == 'comment' for lead in leads), leads
                assert facebook.last_post_scan_stats['skipped_ads'] == 1
                source = dict(url=source_url, message='Bên em bán bếp từ', source_url='https://www.facebook.com/groups/demo/', engagement=20)
                results = facebook.find_comment_buyers(source)
                assert {x['id'] for x in results} == {'1', '3'}, results
                assert results[0]['author'] == 'Khách 1', results
                assert results[0]['message'] == 'Xin giá với', results
                result = facebook.comment_on_post(source_url, 'Bình luận vào bài')
                assert result['sent']
                assert page.evaluate('window.postSent') == 'Bình luận vào bài'
                assert not page.evaluate('Boolean(window.wrongTarget)')
                assert not page.evaluate('Boolean(window.sent)')
                result = facebook.comment_on_post(source_url+'?comment_id=1', 'Tư vấn fixture')
                assert result['sent'] and result['target_type'] == 'comment'
                assert page.evaluate('window.sent') == ['1']
                assert page.locator('#post-editor').inner_text() == ''
                try:
                    facebook.comment_on_post(source_url+'?comment_id=999', 'Không được gửi')
                    raise AssertionError('Missing target must fail')
                except RuntimeError:
                    pass
                assert not page.evaluate('Boolean(window.sent)')
                stop = threading.Event(); stop.set()
                assert facebook.find_comment_buyers(source, cancel_event=stop) == []
                browser.close()
        """)
        result = subprocess.run([sys.executable, '-c', script], capture_output=True,
                                text=True, encoding='utf-8', env=dict(os.environ, PYTHONIOENCODING='utf-8'), timeout=45)
        if result.returncode == 77:
            self.skipTest('Playwright Chromium is not installed')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
