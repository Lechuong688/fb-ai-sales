"""Audience discovery, reviewed campaigns, recurring care and daily activity."""
import csv
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QDate, QDateTime, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDateTimeEdit, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget, QHeaderView)

from backend.browser.pool import browser_pool
from backend.facebook.parsers.post_date import VIETNAM_TZ
from backend.services.account_service import AccountService
from backend.services.group_service import GroupService
from backend.services.outreach_service import (ACTIONS, JOB_STATUSES, RESULT_STATUSES,
    OutreachService, local_now, normalize_target)
from backend.services.outreach_scheduler import OutreachScheduler
from backend.signals import signals
from backend.utils.task_control import TaskControl
from frontend.pages.base_page import BasePage
from frontend.widgets.base_table import BaseTable
from frontend.layouts.flow_layout import FlowLayout


KINDS = {'group': 'Nhóm', 'person': 'Người dùng', 'thread': 'Hội thoại', 'post': 'Bài viết'}


def readonly(value, data=None):
    item = QTableWidgetItem(str(value))
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    item.setToolTip(str(value))
    if data is not None:
        item.setData(Qt.UserRole, data)
    return item


class MessengerPage(BasePage):
    def __init__(self, service=None, start_scheduler=True):
        super().__init__('Kết nối & chăm sóc',
            'Tìm đúng nhóm và người dùng, chuẩn bị nội dung, lên lịch và theo dõi kết quả từng ngày.',
            buttons=[('Làm mới', self.refresh), ('Nạp nhóm đã tham gia', self.import_groups),
                     ('Thêm đối tượng', self.add_target), ('Gắn ngành / khu vực', self.tag_selected)])
        self.service = service or OutreachService()
        self.scheduler = OutreachScheduler(self.service, parent=self, start=start_scheduler)
        self.search_profile = ''
        self.search_control = TaskControl()
        self.media_paths = []
        self._history_rows = []
        self.toolbar.search.setPlaceholderText('Lọc danh sách đối tượng…')
        top = FlowLayout()
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumContentsLength(16)
        self.profile_combo.setMaximumWidth(280)
        top.addWidget(QLabel('Profile Facebook'))
        top.addWidget(self.profile_combo)
        self.scheduler_enabled = QCheckBox('Chạy các lịch đến hạn khi ứng dụng đang mở')
        enabled = self.service.scheduler_enabled()
        self.scheduler_enabled.setChecked(enabled)
        self.scheduler.enabled = enabled
        self.scheduler_enabled.toggled.connect(self.toggle_scheduler)
        top.addWidget(self.scheduler_enabled)
        self.layout.addLayout(top)
        self.notice = QLabel('Lịch chỉ chạy khi đúng profile đang đăng nhập và rảnh. Ngành/khu vực là nhãn tìm kiếm do bạn chọn.')
        self.notice.setWordWrap(True)
        self.notice.setObjectName('infoNotice')
        self.layout.addWidget(self.notice)
        self.tabs = QTabWidget()
        self.tabs.setObjectName('outreachTabs')
        self.tabs.setUsesScrollButtons(True)
        self.layout.addWidget(self.tabs, 1)
        self.build_audience()
        self.build_campaign()
        self.build_jobs()
        self.build_history()
        self.scheduler.changed.connect(self.refresh_activity)
        self.scheduler.error.connect(lambda message: self.notice.setText(f'Lỗi đọc lịch: {message}'))
        signals.outreach_discovered.connect(self.discovered, Qt.QueuedConnection)
        signals.outreach_finished.connect(self.finished, Qt.QueuedConnection)
        signals.outreach_progress.connect(self.search_progress, Qt.QueuedConnection)
        signals.facebook_task_status.connect(self.task_status, Qt.QueuedConnection)
        signals.facebook_login.connect(self.refresh_profiles)
        signals.facebook_logout.connect(self.refresh_profiles)
        self.profile_combo.currentIndexChanged.connect(self.refresh)
        self.toolbar.search.textChanged.connect(self.refresh_targets)
        self.refresh_profiles()

    def build_audience(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.industry_input = QLineEdit()
        self.industry_input.setPlaceholderText('Ví dụ: gara ô tô, nội thất, gia dụng')
        self.region_input = QLineEdit()
        self.region_input.setPlaceholderText('Ví dụ: Hà Nội, Đà Nẵng, TP.HCM')
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText('Từ khóa bổ sung hoặc tên nhóm / người dùng')
        self.search_kind = QComboBox()
        self.search_kind.addItem('Tìm nhóm Facebook', 'group')
        self.search_kind.addItem('Tìm người dùng Facebook', 'person')
        form.addRow('Ngành / lĩnh vực', self.industry_input)
        form.addRow('Khu vực', self.region_input)
        form.addRow('Từ khóa', self.keyword_input)
        form.addRow('Loại tìm kiếm', self.search_kind)
        layout.addLayout(form)
        actions = FlowLayout()
        self.search_button = QPushButton('Tìm trên Facebook')
        self.search_button.clicked.connect(self.discover)
        self.stop_search_button = QPushButton('Dừng tìm')
        self.stop_search_button.setEnabled(False)
        self.stop_search_button.clicked.connect(lambda: self.search_control.stop())
        self.kind_filter = QComboBox()
        self.kind_filter.addItem('Tất cả loại', '')
        for key, label in KINDS.items():
            self.kind_filter.addItem(label, key)
        actions.addWidget(self.search_button)
        actions.addWidget(self.stop_search_button)
        actions.addWidget(self.kind_filter)
        for label, handler in [('Chọn 10 dòng đầu', self.select_targets), ('Bỏ chọn', self.clear_targets),
                               ('Mở đối tượng trong nick', self.open_audience_target),
                               ('Tạo đích nhắn tin từ UID', self.create_threads), ('Xóa khỏi danh sách', self.remove_selected)]:
            button = QPushButton(label)
            button.clicked.connect(handler)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.target_count = QLabel('0 đối tượng đã chọn')
        layout.addWidget(self.target_count)
        self.target_table = BaseTable()
        self.target_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.target_table.horizontalHeader().setStretchLastSection(False)
        self.target_table.setColumnCount(8)
        self.target_table.setHorizontalHeaderLabels(['Chọn', 'Tên', 'Loại', 'Ngành', 'Khu vực', 'Nhóm đã đồng bộ', 'Liên kết', 'Mô tả tìm kiếm'])
        for column, width in ((0, 50), (1, 200), (3, 160), (4, 130), (6, 240), (7, 280)):
            self.target_table.setColumnWidth(column, width)
        self.target_table.itemChanged.connect(self.update_selection)
        layout.addWidget(self.target_table, 1)
        self.tabs.addTab(page, '1. Đối tượng')
        for field in (self.industry_input, self.region_input):
            field.textChanged.connect(self.refresh_targets)
        self.kind_filter.currentIndexChanged.connect(self.refresh_targets)

    def build_campaign(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.campaign_name = QLineEdit()
        self.campaign_name.setPlaceholderText('Ví dụ: Chăm sóc khách gia dụng Hà Nội')
        self.action_combo = QComboBox()
        for key, label in ACTIONS.items():
            self.action_combo.addItem(label, key)
        self.content_input = QTextEdit()
        self.content_input.setPlaceholderText('Nội dung riêng cho từng người: {ten}, ngành {nganh}, khu vực {khu_vuc}')
        self.content_input.setMaximumHeight(150)
        self.run_at = QDateTimeEdit(QDateTime.fromString(local_now().strftime('%Y-%m-%d %H:%M:%S'), 'yyyy-MM-dd HH:mm:ss'))
        self.run_at.setCalendarPopup(True)
        self.run_at.setDisplayFormat('dd/MM/yyyy HH:mm')
        self.repeat_input = QSpinBox()
        self.repeat_input.setRange(0, 365)
        self.repeat_input.setSpecialValueText('Một lần')
        self.repeat_input.setSuffix(' ngày')
        self.limit_input = QSpinBox()
        self.limit_input.setRange(1, 500)
        self.limit_input.setValue(20)
        self.gap_input = QSpinBox()
        self.gap_input.setRange(0, 86400)
        self.gap_input.setValue(60)
        self.gap_input.setSuffix(' giây')
        form.addRow('Tên lịch', self.campaign_name)
        form.addRow('Tác vụ', self.action_combo)
        form.addRow('Nội dung', self.content_input)
        form.addRow('Bắt đầu (UTC+7)', self.run_at)
        form.addRow('Lặp lại', self.repeat_input)
        form.addRow('Tối đa lượt tác vụ / ngày / nick', self.limit_input)
        form.addRow('Khoảng nghỉ giữa tác vụ của nick', self.gap_input)
        layout.addLayout(form)
        files = QHBoxLayout()
        media_button = QPushButton('Chọn ảnh / video cho bài đăng')
        media_button.clicked.connect(self.choose_media)
        clear_media = QPushButton('Bỏ tệp')
        clear_media.clicked.connect(self.clear_media)
        self.media_label = QLabel('Chưa chọn tệp')
        self.media_label.setWordWrap(True)
        files.addWidget(media_button)
        files.addWidget(clear_media)
        files.addWidget(self.media_label, 1)
        layout.addLayout(files)
        info = QLabel('Chọn tối đa 10 đối tượng ở tab 1. Đăng bài dùng nhóm đã đồng bộ của nick; nhắn tin dùng đúng link hội thoại. '
                      'Tương tác là thích một bài chưa thích của người dùng/bài đã chọn. Chỉ đăng bài và tương tác có lịch lặp.')
        info.setWordWrap(True)
        layout.addWidget(info)
        self.schedule_button = QPushButton('Xem nội dung và duyệt lịch')
        self.schedule_button.clicked.connect(self.schedule_selected)
        layout.addWidget(self.schedule_button)
        layout.addStretch()
        self.tabs.addTab(page, '2. Nội dung và lịch')
        self.action_combo.currentIndexChanged.connect(self.action_changed)
        self.action_changed()

    def build_jobs(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        actions = FlowLayout()
        for label, operation in [('Tạm dừng lịch đã chọn', 'pause'), ('Tiếp tục lịch đã chọn', 'resume'), ('Hủy lịch đã chọn', 'cancel')]:
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, op=operation: self.control_jobs(op))
            actions.addWidget(button)
        open_button = QPushButton('Mở đích trong đúng profile')
        open_button.clicked.connect(self.open_job_target)
        actions.addWidget(open_button)
        layout.addLayout(actions)
        hint = QLabel('Lịch chờ được giữ khi tắt ứng dụng. Tác vụ bị gián đoạn chuyển sang Cần kiểm tra sau 10 phút; '
                      'không tự gửi lại. Hủy lịch trước khi tạo lại tác vụ đã kiểm tra. Đang chạy sẽ dừng ở điểm kiểm tra tiếp theo.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.jobs_table = BaseTable()
        self.jobs_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.jobs_table.horizontalHeader().setStretchLastSection(False)
        self.jobs_table.setColumnCount(9)
        self.jobs_table.setHorizontalHeaderLabels(['Chọn', 'Tên lịch', 'Nick', 'Tác vụ', 'Đối tượng', 'Lần chạy tới (UTC+7)', 'Lặp', 'Trạng thái', 'Kết quả gần nhất'])
        self.jobs_table.setColumnWidth(4, 240)
        self.jobs_table.setColumnWidth(5, 180)
        self.jobs_table.setColumnWidth(8, 350)
        layout.addWidget(self.jobs_table, 1)
        self.tabs.addTab(page, '3. Hàng đợi')

    def build_history(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        filters = FlowLayout()
        now = local_now()
        self.history_day = QDateEdit(QDate(now.year, now.month, now.day))
        self.history_day.setCalendarPopup(True)
        self.history_day.setDisplayFormat('dd/MM/yyyy')
        self.history_action = QComboBox()
        self.history_action.addItem('Tất cả tác vụ', '')
        for key, label in ACTIONS.items():
            self.history_action.addItem(label, key)
        self.history_all = QCheckBox('Tất cả nick')
        self.history_query = QLineEdit()
        self.history_query.setPlaceholderText('Tìm người, nhóm, nội dung hoặc trạng thái…')
        export = QPushButton('Xuất CSV ngày đang xem')
        export.clicked.connect(self.export_history)
        for widget in (QLabel('Ngày UTC+7'), self.history_day, self.history_action, self.history_all, self.history_query, export):
            filters.addWidget(widget)
        layout.addLayout(filters)
        self.history_summary = QLabel()
        layout.addWidget(self.history_summary)
        self.history_table = BaseTable()
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.history_table.horizontalHeader().setStretchLastSection(False)
        self.history_table.setColumnCount(8)
        self.history_table.setHorizontalHeaderLabels(['Thời gian (UTC+7)', 'Nick', 'Tác vụ', 'Tên', 'Đích', 'Trạng thái', 'Kết quả', 'Nội dung'])
        self.history_table.setColumnWidth(0, 175)
        self.history_table.setColumnWidth(2, 160)
        self.history_table.setColumnWidth(3, 170)
        self.history_table.setColumnWidth(5, 150)
        self.history_table.setColumnWidth(4, 230)
        self.history_table.setColumnWidth(6, 350)
        layout.addWidget(self.history_table, 1)
        self.tabs.addTab(page, '4. Lịch sử hàng ngày')
        self.history_day.dateChanged.connect(self.refresh_history)
        self.history_action.currentIndexChanged.connect(self.refresh_history)
        self.history_all.toggled.connect(self.refresh_history)
        self.history_query.textChanged.connect(self.refresh_history)

    def profile(self):
        return self.profile_combo.currentData() or ''

    def toggle_scheduler(self, enabled):
        try:
            self.service.set_scheduler_enabled(enabled)
            self.scheduler.enabled = enabled
            self.notice.setText('Đã bật lịch đến hạn.' if enabled else 'Đã dừng nhận lịch mới; tác vụ đang chạy có thể hoàn tất. Trạng thái này được giữ khi mở lại ứng dụng.')
        except Exception as exc:
            self.scheduler.enabled = False
            self.notice.setText(f'Không lưu được trạng thái chạy lịch: {exc}. Đã dừng nhận lịch mới.')

    def refresh_profiles(self, *_args):
        current = self.profile()
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItem('Chọn profile', '')
        for account in AccountService().get_all():
            if account.profile:
                self.profile_combo.addItem(f'{account.name or account.profile} · {account.profile}', account.profile)
        self.profile_combo.setCurrentIndex(max(0, self.profile_combo.findData(current)))
        self.profile_combo.blockSignals(False)
        self.refresh()

    def refresh(self, *_args):
        if not hasattr(self, 'target_table'):
            return
        try:
            self.refresh_targets()
            self.refresh_activity()
        except Exception as exc:
            self.notice.setText(f'Không tải được dữ liệu: {exc}')

    def refresh_targets(self, *_args):
        if not hasattr(self, 'target_table'):
            return
        rows = self.service.targets(self.profile(), self.kind_filter.currentData() or '',
            self.industry_input.text(), self.region_input.text(), self.toolbar.search.text())
        table = self.target_table
        selected = {row['id'] for row in self.selected_targets()}
        table.blockSignals(True)
        table.setSortingEnabled(False)
        table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            check = readonly('', row)
            check.setFlags(check.flags() | Qt.ItemIsUserCheckable)
            check.setCheckState(Qt.Checked if row['id'] in selected else Qt.Unchecked)
            table.setItem(index, 0, check)
            values = [row['name'], KINDS[row['kind']], row['industry'], row['region'],
                      'Đã đồng bộ' if row['joined'] else '', row['url'], row['description']]
            for column, value in enumerate(values, 1):
                table.setItem(index, column, readonly(value))
        table.setSortingEnabled(True)
        table.blockSignals(False)
        self.update_selection()

    def selected_targets(self):
        if not hasattr(self, 'target_table'):
            return []
        return [self.target_table.item(row, 0).data(Qt.UserRole) for row in range(self.target_table.rowCount())
                if self.target_table.item(row, 0) and self.target_table.item(row, 0).checkState() == Qt.Checked]

    def update_selection(self, *_args):
        self.target_count.setText(f'{len(self.selected_targets())} đối tượng đã chọn · {self.target_table.rowCount()} đang hiện')

    def select_targets(self):
        for row in range(self.target_table.rowCount()):
            self.target_table.item(row, 0).setCheckState(Qt.Checked if row < 10 else Qt.Unchecked)

    def clear_targets(self):
        for row in range(self.target_table.rowCount()):
            self.target_table.item(row, 0).setCheckState(Qt.Unchecked)

    def ready_worker(self, profile=None):
        profile = profile or self.profile()
        worker, session = browser_pool.get_worker(profile), browser_pool.get_session(profile)
        if not profile or not worker or not (session and session.running and session.logged_in):
            raise ValueError('Mở và đăng nhập đúng profile trong Tài khoản Facebook trước.')
        if worker.operation_active:
            raise ValueError('Profile đang bận. Đợi tác vụ hiện tại hoàn tất.')
        return worker

    def discover(self):
        try:
            worker = self.ready_worker()
            if self.search_profile:
                raise ValueError('Đang có lượt tìm kiếm chưa kết thúc.')
            if not any(field.text().strip() for field in (self.keyword_input, self.industry_input, self.region_input)):
                raise ValueError('Nhập ngành, khu vực hoặc từ khóa tìm kiếm.')
            self.search_control = TaskControl()
            self.search_profile = self.profile()
            self.scheduler.suspended_profiles.add(self.search_profile)
            self.search_button.setEnabled(False)
            self.stop_search_button.setEnabled(True)
            self.profile_combo.setEnabled(False)
            worker.outreach_search_requested.emit(dict(kind=self.search_kind.currentData(), query=self.keyword_input.text().strip(),
                industry=self.industry_input.text().strip(), region=self.region_input.text().strip(),
                limit=50, control=self.search_control, service=self.service))
            self.notice.setText('Đang tìm trên Facebook bằng profile đã chọn; chưa gửi yêu cầu kết nối.')
        except Exception as exc:
            self.notice.setText(str(exc))

    def end_search(self):
        self.scheduler.suspended_profiles.discard(self.search_profile)
        self.search_profile = ''
        self.search_button.setEnabled(True)
        self.stop_search_button.setEnabled(False)
        self.profile_combo.setEnabled(True)

    def discovered(self, profile, rows):
        if profile == self.search_profile:
            self.end_search()
            self.refresh_targets()
            self.notice.setText(f'Đã lưu {len(rows)} kết quả tìm kiếm. Xem đối tượng trước khi chọn tác vụ.')

    def search_progress(self, profile, progress):
        if profile == self.search_profile:
            self.notice.setText(f"Đang tìm: {progress.get('found', 0)} đối tượng, lượt cuộn {progress.get('scrolls', 0)}.")

    def task_status(self, profile, task, active):
        if task == 'outreach_search' and not active and profile == self.search_profile:
            self.end_search()

    def finished(self, profile, result):
        if profile == self.search_profile and 'job_id' not in result:
            self.end_search()
        self.refresh_activity()
        if profile == self.profile():
            self.notice.setText(result.get('error') or result.get('message') or 'Đã cập nhật lịch sử.')

    def import_groups(self):
        try:
            if not self.profile():
                raise ValueError('Chọn profile trước.')
            rows = [dict(kind='group', url=group.url, name=group.name, joined=True)
                    for group in GroupService().get_for_profile(self.profile())]
            count = self.service.save_targets(self.profile(), rows)
            self.refresh_targets()
            self.notice.setText(f'Đã nạp {count} nhóm. Chọn nhóm rồi gắn ngành/khu vực để lập lịch đăng theo tệp.')
        except Exception as exc:
            self.notice.setText(str(exc))

    def add_target(self):
        if not self.profile():
            self.notice.setText('Chọn profile trước khi thêm đối tượng.')
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('Thêm đối tượng')
        form = QFormLayout(dialog)
        kind = QComboBox()
        for key, label in KINDS.items():
            kind.addItem(label, key)
        name, url = QLineEdit(), QLineEdit()
        url.setMinimumWidth(430)
        form.addRow('Loại', kind)
        form.addRow('Tên', name)
        form.addRow('Link Facebook / hội thoại', url)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.service.save_targets(self.profile(), [dict(kind=kind.currentData(), name=name.text(), url=url.text(),
                industry=self.industry_input.text(), region=self.region_input.text())])
            self.refresh_targets()
        except Exception as exc:
            self.notice.setText(str(exc))

    def tag_selected(self):
        targets = self.selected_targets()
        if not targets:
            self.notice.setText('Chọn đối tượng trước khi gắn nhãn.')
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('Gắn nhãn ngành / khu vực')
        form = QFormLayout(dialog)
        industry, region = QLineEdit(self.industry_input.text()), QLineEdit(self.region_input.text())
        form.addRow('Ngành', industry)
        form.addRow('Khu vực', region)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.Accepted:
            self.service.tag_targets(self.profile(), [row['id'] for row in targets], industry.text(), region.text())
            self.refresh_targets()

    def remove_selected(self):
        self.service.remove_targets(self.profile(), [row['id'] for row in self.selected_targets()])
        self.refresh_targets()

    def open_audience_target(self):
        targets = self.selected_targets()
        if len(targets) != 1:
            self.notice.setText('Chọn một đối tượng để mở trong đúng profile.')
            return
        try:
            self.ready_worker().outreach_open_requested.emit(targets[0]['url'])
        except Exception as exc:
            self.notice.setText(str(exc))

    def create_threads(self):
        rows = []
        for row in self.selected_targets():
            if row['kind'] != 'person':
                continue
            parsed = urlparse(row['url'])
            uid = (parse_qs(parsed.query).get('id') or [parsed.path.strip('/')])[0]
            if uid.isdigit():
                rows.append(dict(row, kind='thread', url=f'https://www.facebook.com/messages/t/{uid}/'))
        if rows:
            self.service.save_targets(self.profile(), rows)
            self.kind_filter.setCurrentIndex(self.kind_filter.findData('thread'))
            self.refresh_targets()
        self.notice.setText(f'Đã tạo {len(rows)} đích từ UID. Với tên tài khoản, mở đúng hội thoại rồi thêm link messages/t/UID vào danh sách.')

    def action_changed(self):
        action = self.action_combo.currentData()
        self.repeat_input.setEnabled(action in {'group_post', 'engage'})
        if action not in {'group_post', 'engage'}:
            self.repeat_input.setValue(0)
        self.content_input.setEnabled(action in {'group_post', 'message'})

    def choose_media(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Ảnh / video cho bài đăng', '', 'Ảnh / video (*.jpg *.jpeg *.png *.webp *.mp4 *.mov);;Tất cả (*)')
        if paths:
            self.media_paths = paths
            self.media_label.setText('\n'.join(paths))

    def clear_media(self):
        self.media_paths = []
        self.media_label.setText('Chưa chọn tệp')

    def campaign_options(self):
        action = self.action_combo.currentData()
        return dict(profile=self.profile(), campaign=self.campaign_name.text().strip(), action=action,
            targets=self.selected_targets(), content=self.content_input.toPlainText() if action in {'message', 'group_post'} else '',
            media=self.media_paths if action == 'group_post' else [],
            run_at=self.run_at.dateTime().toPython().replace(tzinfo=VIETNAM_TZ), repeat_days=self.repeat_input.value(),
            daily_limit=self.limit_input.value(), gap_seconds=self.gap_input.value())

    def schedule_selected(self):
        try:
            options = self.campaign_options()
            prepared = self.service.prepare_schedule(**options)
            if options['action'] == 'group_post':
                joined = {normalize_target('group', group.url) for group in GroupService().get_for_profile(self.profile())}
                if any(row['target'] not in joined for row in prepared):
                    raise ValueError('Đăng bài chỉ dùng nhóm đã đồng bộ của đúng nick. Tham gia rồi quét lại trong Groups trước.')
            dialog = QDialog(self)
            dialog.setWindowTitle('Duyệt đối tượng, nội dung và lịch')
            dialog.resize(920, 500)
            layout = QVBoxLayout(dialog)
            label = QLabel(f"{ACTIONS[options['action']]} · Nick {self.profile()} · {options['run_at'].strftime('%d/%m/%Y %H:%M')} UTC+7\n"
                           f"{len(prepared)} đích · Lặp {options['repeat_days']} ngày (0 = một lần) · Tối đa {options['daily_limit']} lượt/ngày · Nghỉ {options['gap_seconds']} giây")
            label.setWordWrap(True)
            layout.addWidget(label)
            table = QTableWidget(len(prepared), 3)
            table.setHorizontalHeaderLabels(['Đối tượng', 'Link chính xác', 'Nội dung sẽ gửi'])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            table.verticalHeader().setDefaultSectionSize(95)
            for row, target in enumerate(prepared):
                for column, value in enumerate((target['name'], target['target'], target['content'])):
                    table.setItem(row, column, readonly(value))
            layout.addWidget(table)
            if self.media_paths and options['action'] == 'group_post':
                attachments = QLabel('Tệp đính kèm:\n' + '\n'.join(self.media_paths))
                attachments.setWordWrap(True)
                layout.addWidget(attachments)
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.button(QDialogButtonBox.Ok).setText('Duyệt và đưa vào lịch chạy')
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if dialog.exec() != QDialog.Accepted:
                return
            result = self.service.schedule(**options)
            self.notice.setText(f"Đã lưu {len(result['ids'])} tác vụ; bỏ {result['duplicates']} tác vụ trùng. Lịch đến hạn chạy khi nick sẵn sàng.")
            self.refresh_activity()
            self.tabs.setCurrentIndex(2)
        except Exception as exc:
            self.notice.setText(str(exc))

    def refresh_activity(self):
        self.refresh_jobs()
        self.refresh_history()

    def refresh_jobs(self):
        if not hasattr(self, 'jobs_table'):
            return
        table = self.jobs_table
        checked = {row['id'] for row in self.selected_jobs()}
        rows = self.service.list_jobs(self.profile())
        table.setSortingEnabled(False)
        table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            check = readonly('', row)
            check.setFlags(check.flags() | Qt.ItemIsUserCheckable)
            check.setCheckState(Qt.Checked if row['id'] in checked else Qt.Unchecked)
            table.setItem(index, 0, check)
            values = [row['campaign'], row['profile'], ACTIONS[row['action']], row['name'],
                datetime.fromisoformat(row['next_at']).strftime('%d/%m/%Y %H:%M'),
                f"{row['repeat_days']} ngày" if row['repeat_days'] else 'Một lần', JOB_STATUSES[row['status']], row['last_message']]
            for column, value in enumerate(values, 1):
                table.setItem(index, column, readonly(value))
        table.setSortingEnabled(True)

    def selected_jobs(self):
        if not hasattr(self, 'jobs_table'):
            return []
        return [self.jobs_table.item(row, 0).data(Qt.UserRole) for row in range(self.jobs_table.rowCount())
                if self.jobs_table.item(row, 0) and self.jobs_table.item(row, 0).checkState() == Qt.Checked]

    def control_jobs(self, operation):
        self.service.control([row['id'] for row in self.selected_jobs()], operation)
        self.refresh_activity()

    def open_job_target(self):
        selected = self.selected_jobs()
        if len(selected) != 1:
            self.notice.setText('Chọn một lịch để mở đúng đích trong profile của lịch đó.')
            return
        try:
            self.ready_worker(selected[0]['profile']).outreach_open_requested.emit(selected[0]['target'])
        except Exception as exc:
            self.notice.setText(str(exc))

    @staticmethod
    def history_values(row):
        return [datetime.fromisoformat(row['created_at']).strftime('%d/%m/%Y %H:%M:%S'), row['profile'],
            ACTIONS[row['action']], row['name'], row['target'], RESULT_STATUSES.get(row['status'], row['status']),
            row['message'], row['content']]

    def refresh_history(self, *_args):
        if not hasattr(self, 'history_table'):
            return
        self._history_rows = (self.service.history(self.history_day.date().toPython(),
            '' if self.history_all.isChecked() else self.profile(), self.history_action.currentData() or '', self.history_query.text())
            if self.history_all.isChecked() or self.profile() else [])
        rows = self._history_rows
        counts = {status: sum(row['status'] == status for row in rows) for status in RESULT_STATUSES}
        self.history_summary.setText(f"{len(rows)} lượt · {sum(counts[k] for k in ('sent', 'submitted', 'pending', 'done'))} đã thực hiện · "
                                     f"{counts['failed']} lỗi · {counts['review']} cần kiểm tra · {counts['skipped']} không cần thực hiện")
        table = self.history_table
        table.setSortingEnabled(False)
        table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            for column, value in enumerate(self.history_values(row)):
                table.setItem(index, column, readonly(value))
        table.setSortingEnabled(True)

    def export_history(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Xuất lịch sử theo bộ lọc', 'lich-su-ket-noi.csv', 'CSV (*.csv)')
        if not path:
            return
        try:
            with open(path, 'w', newline='', encoding='utf-8-sig') as stream:
                writer = csv.writer(stream)
                writer.writerow([self.history_table.horizontalHeaderItem(i).text() for i in range(8)])
                for row in self._history_rows:
                    writer.writerow(["'" + str(value) if str(value).startswith(('=', '+', '-', '@')) else value
                                     for value in self.history_values(row)])
            self.notice.setText(f'Đã xuất {len(self._history_rows)} lượt theo bộ lọc.')
        except OSError as exc:
            self.notice.setText(f'Không xuất được lịch sử: {exc}')
