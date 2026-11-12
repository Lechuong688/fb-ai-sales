"""Real browser DOM regression using intercepted fixture pages, never Facebook."""

import os
import subprocess
import sys
import textwrap
import unittest


class RecentGroupDOMTests(unittest.TestCase):
    def test_recent_post_dates_and_tooltip_with_real_playwright(self):
        script = textwrap.dedent("""
            from pathlib import Path
            from types import SimpleNamespace
            from datetime import datetime,timedelta
            from PySide6.QtCore import QObject,QCoreApplication,QTimer,Signal,Slot
            from playwright.sync_api import sync_playwright
            from backend.workers.browser_thread import BrowserThread
            from backend.browser.facebook import FacebookBrowser
            from backend.facebook.parsers.post_date import VIETNAM_TZ
            import traceback

            app=QCoreApplication([])
            class Probe(QObject):
                open_requested=Signal()
                scan_requested=Signal()
                def __init__(self):
                    super().__init__()
                    self.opened=False
                    self.done=False
                    self.missing=False
                    self.errors=[]
                    self.open_requested.connect(self.open)
                    self.scan_requested.connect(self.scan)
                @Slot()
                def open(self):
                    try:
                        self.pw=sync_playwright().start()
                        if not Path(self.pw.chromium.executable_path).is_file():
                            self.missing=True
                            self.pw.stop()
                            self.done=True
                            return
                        self.browser=self.pw.chromium.launch(headless=True)
                        self.context=self.browser.new_context()
                        self.context.add_cookies([dict(name='c_user',value='123',domain='.facebook.com',path='/')])
                        self.page=self.context.new_page()
                        self.opened=True
                    except Exception:
                        self.errors.append(traceback.format_exc())
                        self.done=True
                @Slot()
                def scan(self):
                    try:
                        now=datetime(2026,11,1,12,tzinfo=VIETNAM_TZ)
                        def article(number,age=None,label='timestamp'):
                            stamp=f'data-utime="{int((now-age).timestamp())}"' if age is not None else ''
                            return f'<div role="article"><h2><a href="/profile/demo">Demo</a></h2><a href="/groups/demo/posts/{number}/" {stamp} id="date-{number}">{label}</a><div data-ad-preview="message">Cần mua bếp từ</div></div>'
                        html='<main role="main">'+article(1,timedelta(days=30))+article(2,timedelta(days=2))+article(3,None,'2 tuần')+article(4,None,'unknown')
                        html+='<div role="tooltip" style="display:none" id="tip">20 tháng 10, 2026 lúc 10:30</div></main>'
                        html+="<script>document.getElementById('date-3').addEventListener('mouseenter',()=>document.getElementById('tip').style.display='block');document.getElementById('date-3').addEventListener('mouseleave',()=>document.getElementById('tip').style.display='none')</script>"
                        self.context.route('**/*',lambda route:route.fulfill(status=200,content_type='text/html; charset=utf-8',body=html))
                        facebook=FacebookBrowser(SimpleNamespace(page=self.page,context=self.context))
                        posts=facebook.find_buying_posts('https://www.facebook.com/groups/demo/', ['cần mua'],
                                                        now=now,scroll_count=1,group_only=True)
                        assert {post['id'] for post in posts}=={'2','3'},(posts,facebook.last_post_scan_stats,self.page.locator('body').inner_text())
                        assert facebook.last_post_scan_stats['skipped_old']==1
                        assert facebook.last_post_scan_stats['skipped_unknown_date']==1
                    except Exception:
                        self.errors.append(traceback.format_exc())
                    finally:
                        self.browser.close()
                        self.pw.stop()
                        self.done=True
            worker=Probe()
            thread=BrowserThread()
            worker.moveToThread(thread)
            thread.finished.connect(worker.deleteLater)
            thread.start()
            worker.open_requested.emit()
            requested=[False]
            def tick():
                if worker.done:
                    app.quit()
                elif worker.opened and not requested[0]:
                    requested[0]=True
                    worker.scan_requested.emit()
            timer=QTimer()
            timer.timeout.connect(tick)
            timer.start(20)
            QTimer.singleShot(20000,app.quit)
            app.exec()
            thread.quit()
            assert thread.wait(5000)
            if worker.missing:raise SystemExit(77)
            assert worker.done and not worker.errors,worker.errors
        """)
        result = subprocess.run(
            [sys.executable, "-X", "faulthandler", "-c", script],
            capture_output=True, text=True, encoding="utf-8",
            env=dict(os.environ, PYTHONIOENCODING="utf-8"), timeout=35,
        )
        if result.returncode == 77:
            self.skipTest("Playwright Chromium is not installed")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
