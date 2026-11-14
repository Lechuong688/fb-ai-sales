import os
import subprocess
import sys
import textwrap
import unittest


class OutreachUITests(unittest.TestCase):
    def test_main_window_opens_outreach_page_and_stops_scheduler_on_close(self):
        script = textwrap.dedent('''
            import os
            import sys
            import tempfile
            from pathlib import Path
            sys.path.insert(0, str(Path.cwd()))
            from PySide6.QtWidgets import QApplication
            app = QApplication([])
            with tempfile.TemporaryDirectory() as directory:
                os.chdir(directory)
                from frontend.main_window import MainWindow
                from backend.database.init_db import init_database
                from backend.database.db import engine
                init_database()
                try:
                    window = MainWindow()
                    page = window.pages['MessengerPage']
                    window.sidebar.setCurrentRow(6)
                    assert window.stack.currentWidget().widget() is page
                    assert page.scheduler.timer.isActive()
                    assert window.sidebar.item(6).toolTip() == 'Kết nối & chăm sóc'
                    window.close()
                    app.processEvents()
                    assert not page.scheduler.enabled
                    assert not page.scheduler.timer.isActive()
                finally:
                    engine.dispose()
                    os.chdir(sys.path[0])
        ''')
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True,
                                encoding='utf-8', env=dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONIOENCODING='utf-8'), timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_audience_filters_review_queue_and_daily_history(self):
        script = textwrap.dedent('''
            import os
            import tempfile
            from datetime import timedelta
            from pathlib import Path
            from types import SimpleNamespace
            from unittest.mock import patch
            from sqlalchemy import create_engine
            from PySide6.QtWidgets import QApplication, QDialog
            from PySide6.QtGui import QFont, QFontDatabase
            from PySide6.QtCore import Qt
            from backend.services.outreach_service import OutreachService, local_now
            from frontend.pages.messenger import MessengerPage
            from frontend.main import load_styles

            app = QApplication([])
            app.setStyle('Fusion')
            font_path = Path('C:/Windows/Fonts/segoeui.ttf')
            if font_path.exists():
                QFontDatabase.addApplicationFont(str(font_path))
            app.setFont(QFont('Segoe UI', 10))
            load_styles(app, Path('frontend').resolve())
            with tempfile.TemporaryDirectory() as directory:
                engine = create_engine(f'sqlite:///{Path(directory)/"outreach.db"}')
                service = OutreachService(engine)
                rows = [dict(kind='group', url='https://facebook.com/groups/123/', name='Hội gia dụng Hà Nội', industry='Gia dụng', region='Hà Nội', joined=True),
                        dict(kind='person', url='https://facebook.com/456/', name='Lan', industry='Gia dụng', region='Hà Nội'),
                        dict(kind='thread', url='https://facebook.com/messages/e2ee/t/789/', name='Khách Lan', industry='Gia dụng', region='Hà Nội')]
                service.save_targets('demo', rows)
                with patch('frontend.pages.messenger.AccountService') as accounts, patch('frontend.pages.messenger.GroupService') as groups:
                    accounts.return_value.get_all.return_value = [SimpleNamespace(profile='demo', name='Nick bán hàng')]
                    groups.return_value.get_for_profile.return_value = [SimpleNamespace(url=rows[0]['url'], name=rows[0]['name'])]
                    page = MessengerPage(service, start_scheduler=False)
                    page.profile_combo.setCurrentIndex(page.profile_combo.findData('demo'))
                    page.resize(1200, 900)
                    page.show()
                    app.processEvents()
                    assert page.tabs.count() == 4
                    assert page.target_table.rowCount() == 3
                    page.industry_input.setText('gia dung')
                    page.region_input.setText('ha noi')
                    assert page.target_table.rowCount() == 3
                    page.kind_filter.setCurrentIndex(page.kind_filter.findData('thread'))
                    assert page.target_table.rowCount() == 1
                    page.select_targets()
                    page.campaign_name.setText('Kết nối khách gia dụng Hà Nội')
                    page.action_combo.setCurrentIndex(page.action_combo.findData('message'))
                    page.content_input.setPlainText('Chào {ten}, em hỗ trợ {nganh} ở {khu_vuc}.')
                    with patch('frontend.pages.messenger.QDialog.exec', return_value=QDialog.Rejected):
                        page.schedule_selected()
                    assert service.list_jobs() == []
                    with patch('frontend.pages.messenger.QDialog.exec', return_value=QDialog.Accepted):
                        page.schedule_selected()
                    jobs = service.list_jobs()
                    assert len(jobs) == 1, page.notice.text()
                    assert jobs[0]['content'] == 'Chào Khách Lan, em hỗ trợ Gia dụng ở Hà Nội.'
                    assert jobs[0]['target'] == 'https://www.facebook.com/messages/e2ee/t/789/'
                    assert page.jobs_table.rowCount() == 1
                    page.jobs_table.item(0, 0).setCheckState(Qt.Checked)
                    page.control_jobs('pause')
                    assert service.list_jobs()[0]['status'] == 'paused'
                    page.control_jobs('resume')
                    assert service.list_jobs()[0]['status'] == 'queued'
                    job = service.claim(jobs[0]['id'])
                    assert job
                    service.finish(job['id'], job['token'], 'sent', 'Đã thấy tin trong hội thoại')
                    page.refresh_activity()
                    assert page.history_table.rowCount() == 1
                    path = str(Path(directory)/'activity.csv')
                    with patch('frontend.pages.messenger.QFileDialog.getSaveFileName', return_value=(path, 'CSV')):
                        page.export_history()
                    assert 'Chào Khách Lan' in Path(path).read_text(encoding='utf-8-sig')
                    capture = os.environ.get('OUTREACH_UI_CAPTURE')
                    if capture:
                        output = Path(capture)
                        output.mkdir(parents=True, exist_ok=True)
                        for width in (1200, 760):
                            page.resize(width, 900)
                            for tab in range(4):
                                page.tabs.setCurrentIndex(tab)
                                app.processEvents()
                                assert page.grab().save(str(output/f'outreach-{width}-{tab}.png'))
                    page.close()
                    page.deleteLater()
                    app.processEvents()
                engine.dispose()
        ''')
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True,
                                encoding='utf-8', env=dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONIOENCODING='utf-8'), timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
