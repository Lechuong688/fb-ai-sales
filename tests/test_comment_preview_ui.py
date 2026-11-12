import os
import subprocess
import sys
import textwrap
import unittest


class CommentPreviewUITests(unittest.TestCase):
    def test_scan_defaults_to_owned_groups_and_stop_keeps_profile_open(self):
        script = textwrap.dedent("""
            from pathlib import Path
            from types import SimpleNamespace
            import tempfile
            import threading
            from unittest.mock import Mock, patch
            from PySide6.QtWidgets import QApplication
            from backend.services.account_service import AccountService
            from backend.services.comment_rules import CommentRuleStore
            from frontend.pages.comment_page import CommentPage

            app = QApplication([])
            account = SimpleNamespace(profile='demo', name='Demo')
            worker = Mock(operation_active=False)
            worker.scan_cancel_event = threading.Event()
            worker.cancel_event = threading.Event()
            groups = [SimpleNamespace(name=f'Group {i}', url=f'https://www.facebook.com/groups/{i}/') for i in (1,2)]
            with tempfile.TemporaryDirectory() as directory, \\
                 patch.object(AccountService, '__init__', return_value=None), \\
                 patch.object(AccountService, 'get_all', return_value=[account]), \\
                 patch('frontend.pages.comment_page.GroupService') as service, \\
                 patch('frontend.pages.comment_page.load_company_catalog', return_value=None), \\
                 patch('frontend.pages.comment_page.CommentRuleStore', return_value=CommentRuleStore(Path(directory)/'rules.json')), \\
                 patch('frontend.pages.comment_page.browser_pool') as pool:
                service.return_value.get_for_profile.return_value = groups
                pool.get_session.return_value = SimpleNamespace(running=True,logged_in=True)
                pool.get_worker.return_value = worker
                page = CommentPage()
                assert page.source_combo.currentData() == '__all_groups__'
                assert all(page.source_combo.itemData(i) != 'https://www.facebook.com/' for i in range(page.source_combo.count()))
                page.scan_posts()
                request = worker.scan_requested.emit.call_args.args[0]
                assert request['source_urls'] == [group.url for group in groups]
                assert request['max_age_days'] == 15
                assert request['scroll_count'] == 120
                assert request['seconds_per_group'] == 180
                assert request['max_posts'] == 200
                assert page._scan_active and page.stop_scan_button.isEnabled()
                assert not page.account_combo.isEnabled()
                page._show_posts('demo', [])
                assert not page.scan_button.isEnabled()
                page.stop_scan_button.click()
                assert worker.scan_cancel_event.is_set()
                assert not worker.cancel_event.is_set()
                pool.close.assert_not_called()
                page._scan_progress('demo', dict(stage='summary', reason='cancelled', groups_scanned=1,
                                                groups_total=2, found_total=0, skipped_old=5, skipped_unknown_date=3))
                assert '15 ngày' in page.status_label.text()
                assert '5' in page.status_label.text() and '3' in page.status_label.text()
                page._task_status('demo','scan',False)
                assert page.scan_button.isEnabled()
                assert not page.stop_scan_button.isEnabled()
                assert page.account_combo.isEnabled()
                page.close()
        """)
        result = subprocess.run(
            [sys.executable, "-X", "faulthandler", "-c", script],
            capture_output=True, text=True, encoding="utf-8",
            env=dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8"), timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_company_catalog_is_default_and_previews_do_not_send(self):
        script = textwrap.dedent("""
            import tempfile
            from pathlib import Path
            from unittest.mock import patch
            from PySide6.QtCore import QTimer, Qt
            from PySide6.QtWidgets import QApplication, QTableWidget
            from backend.services.account_service import AccountService
            from backend.services.comment_rules import CommentRuleStore
            from backend.services.product_catalog import ProductCatalog
            from frontend.pages.comment_page import CommentPage

            app = QApplication([])
            def item(sku, name, category, stock):
                return dict(sku=sku, name=name, category=category, brand='BOSCH', stock_snapshot=stock,
                            item_type='Hàng hóa', source_sheet='Danh mục', source_row=2)
            catalog = ProductCatalog(dict(schema_version=1, source={'filename':'fixture.xlsx'}, products=[
                item('ABC1234', 'Bếp từ Bosch ABC1234', 'Bếp từ', 2),
                item('XYZ1234', 'Tủ lạnh Bosch XYZ1234', 'Tủ Lạnh', 0),
                item('VTPS', 'Vật tư phát sinh', 'Dịch vụ', 0),
            ]))
            with tempfile.TemporaryDirectory() as directory, \\
                 patch.object(AccountService, '__init__', return_value=None), \\
                 patch.object(AccountService, 'get_all', return_value=[]), \\
                 patch('frontend.pages.comment_page.load_company_catalog', return_value=catalog), \\
                 patch('frontend.pages.comment_page.CommentRuleStore', return_value=CommentRuleStore(Path(directory)/'rules.json')), \\
                 patch('frontend.pages.comment_page.browser_pool') as pool:
                page = CommentPage()
                assert page.catalog_checkbox.isChecked()
                assert not page.products_input.isEnabled()
                page.show_catalog_samples()
                assert page.results.rowCount() == 4
                for row in range(page.results.rowCount()):
                    post = page.results.item(row, 0).data(Qt.UserRole)
                    assert post['status'] in {'draft', 'manual_review'}
                    assert 'ib' in post['comment']
                    assert 'Bên em có' not in post['comment']
                    assert page.results.item(row, 7).text()
                page._select_unsent()
                page.comment_selected()
                pool.get_worker.assert_not_called()
                errors = []
                def inspect_dialog():
                    dialog = app.activeModalWidget()
                    try:
                        table = dialog.findChild(QTableWidget)
                        assert table.rowCount() == 3
                        assert not table.editTriggers()
                    except Exception as exc:
                        errors.append(str(exc))
                    finally:
                        dialog.reject()
                QTimer.singleShot(0, inspect_dialog)
                page.show_catalog()
                assert not errors, errors
                page.catalog_checkbox.setChecked(False)
                assert page.products_input.isEnabled()
                page.close()
            print('Company catalog UI and offline replies passed')
        """)
        result = subprocess.run(
            [sys.executable, "-X", "faulthandler", "-c", script],
            capture_output=True, text=True, encoding="utf-8",
            env=dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8"), timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_offline_review_edit_rules_and_export_never_access_browser(self):
        script = textwrap.dedent("""
            import csv
            import json
            from pathlib import Path
            import tempfile
            from unittest.mock import patch
            from PySide6.QtCore import Qt, QTimer
            from PySide6.QtWidgets import QApplication, QTableWidget, QDialogButtonBox
            from backend.services.account_service import AccountService
            from backend.services.comment_rules import CommentRuleStore
            from backend.services.comment_samples import SAMPLE_CASES
            from frontend.pages.comment_page import CommentPage

            app = QApplication([])
            with tempfile.TemporaryDirectory() as directory, \\
                 patch.object(AccountService, '__init__', return_value=None), \\
                 patch.object(AccountService, 'get_all', return_value=[]), \\
                 patch('frontend.pages.comment_page.browser_pool') as pool, \\
                 patch('frontend.pages.comment_page.CommentRuleStore', return_value=CommentRuleStore(Path(directory)/'rules.json')), \\
                 patch('backend.ai.reply.urlopen', side_effect=AssertionError('No network during offline tests')) as api:
                with patch('frontend.pages.comment_page.load_company_catalog', return_value=None):
                    page = CommentPage()
                page.show_sample_posts()
                assert page.results.rowCount() == len(SAMPLE_CASES)
                row = next(row for row in range(page.results.rowCount())
                           if page.results.item(row, 0).data(Qt.UserRole)['message'] == SAMPLE_CASES[0][0])
                assert 'Bên em có' in page.results.item(row, 6).text()
                page._select_unsent()
                for index in range(page.results.rowCount()):
                    selection = page.results.item(index, 0)
                    if selection.data(Qt.UserRole)['status'] in {'skipped', 'duplicate'}:
                        assert selection.checkState() == Qt.Unchecked
                page._clear_selection()
                page.results.item(row, 0).setCheckState(Qt.Checked)
                page.results.item(row, 6).setText('Bản nháp do người dùng sửa')
                page.comment_selected()
                assert page.results.item(row, 6).text() == 'Bản nháp do người dùng sửa'
                assert 'đang khóa' in page.status_label.text()
                page.comment_input.setPlainText('Nội dung thay thế đã duyệt trên máy')
                page.comment_selected()
                assert page.results.item(row, 6).text() == page.comment_input.toPlainText()

                def edit_dialog():
                    dialog = app.activeModalWidget()
                    table = dialog.findChild(QTableWidget)
                    index = next(index for index in range(table.rowCount())
                                 if table.item(index, 0).data(Qt.UserRole) == 'availability')
                    table.item(index, 1).setText('hỏi hàng mẫu')
                    table.item(index, 2).setText('Bản thử {san_pham}')
                    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click()

                QTimer.singleShot(0, edit_dialog)
                page.edit_rules()
                saved = json.loads((Path(directory)/'rules.json').read_text(encoding='utf-8'))
                assert next(rule for rule in saved if rule['id']=='availability')['reply'] == 'Bản thử {san_pham}'
                page._show_posts(page._pending_profile, [dict(author='=1+1', message='Hỏi hàng mẫu bếp từ', url='sample://edited')])
                assert page.results.item(0, 6).text() == 'Bản thử bếp từ'
                path = Path(directory)/'preview.csv'
                with patch('frontend.pages.comment_page.QFileDialog.getSaveFileName', return_value=(str(path), 'CSV (*.csv)')):
                    page.export_preview()
                with path.open(encoding='utf-8-sig', newline='') as handle:
                    exported = list(csv.reader(handle))
                assert exported[1][0] == "'=1+1"
                assert exported[1][5] == 'Bản thử bếp từ'
                pool.get_worker.assert_not_called()
                api.assert_not_called()
                page.close()
            print('Offline sample review, edits, rule persistence and CSV export passed')
        """)
        result = subprocess.run(
            [sys.executable, "-X", "faulthandler", "-c", script],
            capture_output=True, text=True, encoding="utf-8",
            env=dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8"), timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


    def test_manual_edits_survive_refresh_and_original_post_opens_safely(self):
        script = textwrap.dedent("""
            import tempfile
            from pathlib import Path
            from unittest.mock import patch
            from PySide6.QtWidgets import QApplication
            from backend.services.account_service import AccountService
            from backend.services.comment_rules import CommentRuleStore
            from frontend.pages.comment_page import CommentPage

            app = QApplication([])
            with tempfile.TemporaryDirectory() as directory, \\
                 patch.object(AccountService, '__init__', return_value=None), \\
                 patch.object(AccountService, 'get_all', return_value=[]), \\
                 patch('frontend.pages.comment_page.load_company_catalog', return_value=None), \\
                 patch('frontend.pages.comment_page.CommentRuleStore', return_value=CommentRuleStore(Path(directory)/'rules.json')), \\
                 patch('frontend.pages.comment_page.QDesktopServices.openUrl', return_value=True) as open_url:
                page = CommentPage()
                post = dict(author='Khách', message='Có bác nào có bếp từ này không?', url='sample://bep-tu')
                page._pending_profile = '__samples__'
                page._show_posts('__samples__', [post])
                assert page.results.item(0, 6).text()
                page.results.item(0, 6).setText('Bản nháp tôi đã tự sửa để gửi inbox')
                page._show_posts('__samples__', [post])
                assert page.results.item(0, 6).text() == 'Bản nháp tôi đã tự sửa để gửi inbox'

                page.results.setCurrentCell(0, 2)
                assert not page.open_post_button.isEnabled()
                page.open_source_post()
                open_url.assert_not_called()

                changed = dict(post, message='Cần mua bếp từ loại 3 vùng nấu')
                page._show_posts('__samples__', [changed])
                assert page.results.item(0, 6).text() != 'Bản nháp tôi đã tự sửa để gửi inbox'

                real = dict(changed, url='https://www.facebook.com/groups/123/posts/456/?ref=share')
                page._pending_profile = 'demo'
                page._show_posts('demo', [real])
                page.results.setCurrentCell(0, 2)
                assert page.open_post_button.isEnabled()
                page.open_post_button.click()
                assert open_url.call_count == 1
                assert open_url.call_args.args[0].toString() == 'https://www.facebook.com/groups/123/posts/456/'
                page.close()
        """)
        result = subprocess.run(
            [sys.executable, "-X", "faulthandler", "-c", script],
            capture_output=True, text=True, encoding="utf-8",
            env=dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8"), timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
