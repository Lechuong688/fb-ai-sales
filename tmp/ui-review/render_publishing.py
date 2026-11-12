import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import create_engine
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from frontend.main import load_styles
from frontend.pages.posts import PostPage
from frontend.pages.reports import ReportsPage
from frontend.pages.comment_page import CommentPage
from backend.services.publishing_service import PublishingService

app = QApplication([])
for font_path in ('C:/Windows/Fonts/segoeui.ttf', 'C:/Windows/Fonts/segoeuib.ttf', 'C:/Windows/Fonts/seguiemj.ttf'):
    QFontDatabase.addApplicationFont(font_path)
app.setStyle('Fusion')
app.setFont(QFont('Segoe UI', 10))
load_styles(app, Path('frontend'))
service = PublishingService(create_engine('sqlite://'))
urls = ['https://www.facebook.com/groups/123/', 'https://www.facebook.com/groups/456/']
service.save_collection('Khách hàng thiết bị bếp', 'demo', urls)
service.record('Bếp Chương', [dict(success=True, target=urls[0], kind='group', message='Đã gửi bài. Có thể đang chờ quản trị viên duyệt.')], 'Tư vấn thiết bị bếp phù hợp với nhu cầu của gia đình.')
service.record('Bếp Chương', [dict(success=False, target=urls[1], kind='group', message='Không tìm thấy nút tạo bài viết.')], 'Tư vấn thiết bị bếp phù hợp với nhu cầu của gia đình.')
with patch('frontend.pages.posts.AccountService') as accounts, patch('frontend.pages.posts.GroupService') as groups, patch('frontend.pages.posts.PostDraftService') as drafts, patch('frontend.pages.posts.ProfileLabelService') as labels, patch('frontend.pages.posts.PublishingService', return_value=service), patch('frontend.pages.posts.browser_pool') as pool:
    accounts.return_value.get_all.return_value = [SimpleNamespace(profile='demo', name='Bếp Chương')]
    labels.return_value.get_label.return_value = 'Bếp Chương'
    groups.return_value.get_for_profile.return_value = [SimpleNamespace(name='Hội yêu bếp và thiết bị gia đình', url=url) for url in urls]
    groups.return_value.clean_group_name.side_effect = lambda name, url: name
    drafts.return_value.get_all.return_value = []
    pool.get_session.return_value = SimpleNamespace(running=True, logged_in=True)
    posts = PostPage()
    posts.content_input.setPlainText('Bạn đang tìm thiết bị bếp phù hợp cho gia đình?\nBếp Chương hỗ trợ tư vấn sản phẩm theo nhu cầu và ngân sách. Inbox để được kiểm tra mẫu, tồn kho và báo giá cụ thể nhé!')
    posts._group_selection = {'demo': set(urls)}
    posts._show_groups_for_current_profile()
    posts.resize(1400, 1000)
    posts.show()
    app.processEvents()
    posts.grab().save('tmp/ui-review/fbtool-posts.png')
    posts.hide()
with patch('frontend.pages.comment_page.AccountService') as accounts, patch('frontend.pages.comment_page.GroupService') as groups, patch('frontend.pages.comment_page.PublishingService', return_value=service), patch('frontend.pages.comment_page.browser_pool') as pool:
    accounts.return_value.get_all.return_value = [SimpleNamespace(profile='demo', name='Bếp Chương')]
    groups.return_value.get_for_profile.return_value = [SimpleNamespace(name='Hội yêu bếp', url=url) for url in urls]
    pool.get_session.return_value = SimpleNamespace(running=True, logged_in=True)
    page = CommentPage()
    page.show_catalog_samples()
    page._select_unsent()
    page.resize(1400, 950)
    page.show()
    app.processEvents()
    page.grab().save('tmp/ui-review/fbtool-comment.png')
    page.hide()
reports = ReportsPage(service)
reports.resize(1400, 800)
reports.show()
app.processEvents()
reports.grab().save('tmp/ui-review/fbtool-reports.png')
print('Rendered posts, comment and reports previews with fixture data.')
