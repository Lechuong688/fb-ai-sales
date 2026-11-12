import os
import subprocess
import sys
import textwrap
import unittest


class CustomersUITests(unittest.TestCase):
    def test_follow_up_review_edit_conflicts_export_and_reopen_are_local(self):
        script = textwrap.dedent("""
            import csv
            from datetime import datetime,timedelta
            from pathlib import Path
            import tempfile
            from unittest.mock import Mock,patch
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            from PySide6.QtCore import Qt
            from PySide6.QtWidgets import QApplication,QMessageBox
            from backend.database.repositories.lead_repository import LeadRepository
            from backend.facebook.parsers.post_date import VIETNAM_TZ
            from backend.services.lead_service import LeadService
            from backend.services.comment_rules import LIVE_COMMENTS_ENABLED
            from frontend.pages.customers import CustomersPage
            from frontend.pages.dashboard import DashboardPage

            app=QApplication([])
            now=datetime(2026,11,3,12,tzinfo=VIETNAM_TZ)
            def post(number,text='Cần mua bếp từ cho gia đình'):
                return dict(url=f'https://www.facebook.com/groups/100/posts/{number}/',
                            author='=1+1',message=text,source_name='Hội nhà bếp',
                            source_url='https://www.facebook.com/groups/100/',
                            published_at=(now-timedelta(days=1)).isoformat())
            with tempfile.TemporaryDirectory() as directory:
                engine=create_engine(f'sqlite:///{Path(directory)/"test.db"}')
                factory=sessionmaker(bind=engine,autoflush=False)
                service=LeadService(LeadRepository(engine,factory),clock=lambda:now)
                service.capture_scan('demo',[post(1),post(2)])
                CustomersPage.PAGE_SIZE=1
                page=CustomersPage(service)
                page.show()
                assert page.table.rowCount()==1 and page.next_button.isEnabled()
                page.next_button.click()
                assert page._page==1 and page.previous_button.isEnabled()
                page.previous_button.click()
                lead_id=page._current['id']
                page.draft_input.setPlainText('Nội dung đang sửa')
                page.notes_input.setPlainText('Gọi lại chiều mai')
                assert page._dirty and not page.status_filter.isEnabled()
                service.capture_scan('demo',[post(2,'Cần mua bếp từ ngân sách 5 triệu')])
                app.processEvents()
                assert page.draft_input.toPlainText()=='Nội dung đang sửa'
                page.save_button.click()
                assert page._dirty
                assert service.get(lead_id)['draft_comment']!='Nội dung đang sửa'
                page.reset_button.click()
                assert not page._dirty
                page.draft_input.setPlainText('Bản đã chỉnh và chờ duyệt')
                page.notes_input.setPlainText('Gọi lại khách Hà Nội')
                page.workflow_combo.setCurrentIndex(page.workflow_combo.findData('follow_up'))
                page.save_button.click()
                assert not page._dirty
                assert service.get(lead_id)['notes']=='Gọi lại khách Hà Nội'
                page.approve_button.click()
                assert service.get(lead_id)['review_status']=='approved'
                group_service=Mock()
                group_service.get_all.return_value=[]
                with patch('frontend.widgets.activity_widget.CommentHistoryService') as history:
                    history.return_value.get_recent.return_value=[]
                    dashboard=DashboardPage(lead_service=service,group_service=group_service)
                assert dashboard.customer_card.value_label.text()=='2'
                assert dashboard.ai_card.value_label.text()=='1'
                page.draft_input.setPlainText('Bản được sửa lần hai')
                page.save_button.click()
                app.processEvents()
                assert service.get(lead_id)['review_status']=='pending'
                assert dashboard.ai_card.value_label.text()=='0'
                page.status_filter.setCurrentIndex(page.status_filter.findData('follow_up'))
                assert page._total==1
                page.review_filter.setCurrentIndex(page.review_filter.findData('approved'))
                assert page._total==0 and not page.save_button.isEnabled()
                page.review_filter.setCurrentIndex(0)
                page.toolbar.search.setText('goi lai khach ha noi')
                page._filter_changed()
                assert page._total==1
                target=Path(directory)/'customers.csv'
                with patch('frontend.pages.customers.QFileDialog.getSaveFileName',return_value=(str(target),'CSV (*.csv)')):
                    page.export_csv()
                with target.open(encoding='utf-8-sig',newline='') as handle:
                    exported=list(csv.reader(handle))
                assert len(exported)==2 and exported[1][0]=="'=1+1"
                assert exported[1][-1]=='Gọi lại khách Hà Nội'
                with patch('frontend.pages.customers.QDesktopServices.openUrl') as open_url:
                    page.open_button.click()
                    assert open_url.call_args.args[0].scheme()=='https'
                page.notes_input.setPlainText('Chưa lưu khi thoát')
                with patch('frontend.pages.customers.QMessageBox.question',return_value=QMessageBox.Cancel):
                    assert not page.confirm_close()
                with patch('frontend.pages.customers.QMessageBox.question',return_value=QMessageBox.Save):
                    assert page.confirm_close()
                reopened=CustomersPage(LeadService(LeadRepository(engine,factory),clock=lambda:now))
                saved=service.get(lead_id)
                assert saved['draft_comment']=='Bản được sửa lần hai'
                assert saved['notes']=='Chưa lưu khi thoát'
                assert saved['workflow_status']=='follow_up'
                assert saved['review_status']=='pending'
                reopened.set_available_width(650)
                assert reopened.splitter.orientation()==Qt.Vertical
                reopened.set_available_width(1300)
                assert reopened.splitter.orientation()==Qt.Horizontal
                assert LIVE_COMMENTS_ENABLED is False
                page.close()
                reopened.close()
                dashboard.close()
                engine.dispose()
            print('Local customer follow-up and review passed')
        """)
        result = subprocess.run(
            [sys.executable, "-X", "faulthandler", "-c", script],
            capture_output=True, text=True, encoding="utf-8",
            env=dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8"), timeout=25,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
