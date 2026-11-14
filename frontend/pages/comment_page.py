from PySide6.QtCore import QThread, Qt, Slot, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QMenu,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QTableWidgetItem,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)
import copy
import csv
import uuid
import threading

from backend.browser.pool import browser_pool
from backend.services.account_service import AccountService
from backend.services.group_service import GroupService
from backend.services.profile_label_service import ProfileLabelService
from backend.signals import signals
from backend.workers.reply_suggestion_worker import ReplySuggestionWorker
from frontend.pages.base_page import BasePage
from frontend.widgets.base_table import BaseTable
from frontend.widgets.section_panel import SectionPanel
from frontend.layouts.flow_layout import FlowLayout
from backend.services.comment_rules import (
    CommentRuleStore, DEFAULT_PRODUCTS, DEFAULT_RULES, DEFAULT_BUYER_PHRASES, preview_comments, scan_keywords,
)
from backend.services.comment_samples import sample_posts
from backend.services.product_catalog import load_company_catalog, catalog_sample_posts
from backend.services.catalog_importer import import_catalog
from backend.services.lead_service import LeadService, real_post_url
from backend.services.publishing_service import PublishingService
from backend.utils.text_matching import normalize_text
from backend.utils.task_control import TaskControl


class CommentPage(BasePage):
    """Browse a logged-in profile's feed/groups and review buyer-intent posts."""

    def __init__(self):
        super().__init__(
            title="Tìm khách hàng",
            description=(
                "Tìm đúng nhu cầu, chuẩn bị lời tư vấn phù hợp và quản lý cơ hội bán hàng."
            ),
            buttons=[
                ("🔍 Tìm bài mua hàng", self.scan_posts),
                ("📝 Lưu bản nháp đã chọn", self.comment_selected),
                ("↻ Làm mới nguồn", self.refresh_sources),
            ],
        )
        self.toolbar.set_search_visible(False)
        self.profile_labels = ProfileLabelService()
        self._pending_profile = ""
        self._scan_active = False
        self._suggestion_thread = None
        self._ai_cancel = threading.Event()
        self._ai_control = TaskControl()
        self._scan_control = TaskControl()
        self.rule_store = CommentRuleStore()
        self._rule_load_error = ""
        try:
            self.rules = self.rule_store.load()
        except (ValueError, OSError, TypeError) as exc:
            self.rules = copy.deepcopy(DEFAULT_RULES)
            self._rule_load_error = f"Không đọc được bộ quy tắc đã lưu; đang dùng mặc định: {exc}"
        try:
            self.catalog = load_company_catalog()
        except (ValueError, OSError, TypeError, KeyError) as exc:
            self.catalog = None
            self._rule_load_error += f" Không đọc được danh mục công ty: {exc}"

        source_layout = QGridLayout()
        source_layout.setHorizontalSpacing(12)
        source_layout.setVerticalSpacing(8)

        self.account_combo = QComboBox()
        self.source_combo = QComboBox()
        for combo in (self.account_combo, self.source_combo):
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(15)
        source_layout.addWidget(QLabel("Tài khoản Facebook"), 0, 0)
        source_layout.addWidget(self.account_combo, 1, 0)
        source_layout.addWidget(QLabel("Nhóm / bộ sưu tập"), 0, 1)
        source_layout.addWidget(self.source_combo, 1, 1)
        self.max_posts_input = QSpinBox()
        self.max_posts_input.setRange(1, 500)
        self.max_posts_input.setValue(200)
        self.max_posts_input.setSuffix(" bài")
        self.max_posts_input.setMaximumWidth(170)
        source_layout.addWidget(QLabel("Số bài tối đa"), 0, 2)
        source_layout.addWidget(self.max_posts_input, 1, 2)
        source_layout.setColumnStretch(0, 1)
        source_layout.setColumnStretch(1, 2)
        source_panel = SectionPanel("Nguồn tìm kiếm", "Bài mới · 15 ngày", "01")
        source_panel.body.addLayout(source_layout)
        group_filter_hint = QLabel("Tự lọc tên nhóm theo sản phẩm quan tâm hoặc danh mục công ty; bỏ qua nhóm không liên quan trước khi mở Facebook.")
        group_filter_hint.setWordWrap(True)
        source_panel.body.addWidget(group_filter_hint)
        self.scan_comments_checkbox = QCheckBox("Tìm khách trong bình luận; bài quảng cáo chỉ đọc khi có nhiều bình luận")
        self.scan_comments_checkbox.setChecked(True)
        source_panel.body.addWidget(self.scan_comments_checkbox)
        self.min_ad_comments_input = QSpinBox()
        self.min_ad_comments_input.setRange(1, 10000)
        self.min_ad_comments_input.setValue(10)
        self.min_ad_comments_input.setSuffix(" bình luận")
        comment_threshold = QHBoxLayout()
        comment_threshold.addWidget(QLabel("Chỉ đọc bình luận bài quảng cáo từ"))
        comment_threshold.addWidget(self.min_ad_comments_input)
        comment_threshold.addStretch()
        source_panel.body.addLayout(comment_threshold)
        self.scan_comments_checkbox.toggled.connect(self.min_ad_comments_input.setEnabled)
        self.layout.addWidget(source_panel)

        self.phrases_input = QTextEdit()
        self.phrases_input.setMaximumHeight(58)
        self.phrases_input.setPlaceholderText(
            "Cụm từ thể hiện nhu cầu mua, phân cách bằng dấu phẩy"
        )
        self.phrases_input.setPlainText(
            ", ".join(DEFAULT_BUYER_PHRASES)
        )
        self.products_input = QLineEdit(", ".join(DEFAULT_PRODUCTS))
        self.products_input.setToolTip("Chỉ tạo bình luận cho bài có một sản phẩm trong danh sách này.")
        self.catalog_checkbox = QCheckBox()
        self.catalog_checkbox.setChecked(self.catalog is not None)
        self.catalog_checkbox.toggled.connect(lambda checked: self.products_input.setEnabled(not checked))
        self._update_catalog_info()

        self.comment_input = QTextEdit()
        self.comment_input.setMaximumHeight(82)
        self.comment_input.setPlaceholderText(
            "Tùy chọn: nội dung có sẵn cho các bài đã chọn. Xem và sửa trong hộp duyệt trước khi gửi."
        )
        self.business_context_input = QLineEdit()
        self.business_context_input.setPlaceholderText(
            "Thông tin có thể dùng khi trả lời (tên shop, cách liên hệ...)"
        )

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.addRow("Từ khóa quét bổ sung", self.phrases_input)
        form.addRow("Sản phẩm quan tâm", self.products_input)
        form.addRow("Danh mục hàng hóa", self.catalog_checkbox)
        criteria_panel = SectionPanel("Tiêu chí & nội dung tư vấn", "", "02")
        criteria_panel.body.addLayout(form)
        self.advanced_options = QWidget()
        advanced_form = QFormLayout(self.advanced_options)
        advanced_form.setContentsMargins(0, 4, 0, 0)
        advanced_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        advanced_form.addRow("Thông tin cửa hàng cho AI", self.business_context_input)
        advanced_form.addRow("Nội dung thay thế (tùy chọn)", self.comment_input)
        self.advanced_options.setVisible(False)
        advanced_toggle = self.advanced_toggle = QPushButton("Thông tin cửa hàng & nội dung thay thế  ▾")
        advanced_toggle.setObjectName("disclosureButton")
        advanced_toggle.setCheckable(True)
        advanced_toggle.toggled.connect(self.advanced_options.setVisible)
        advanced_toggle.toggled.connect(lambda checked: advanced_toggle.setText(
            "Thông tin cửa hàng & nội dung thay thế  " + ("▴" if checked else "▾")))
        criteria_panel.body.addWidget(advanced_toggle)
        criteria_panel.body.addWidget(self.advanced_options)
        self.layout.addWidget(criteria_panel)

        self.status_label = QLabel("Chọn tài khoản và nguồn rồi bấm Tìm bài mua hàng.")
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("infoNotice")
        self.layout.addWidget(self.status_label)

        results_tools = FlowLayout()
        results_heading = QLabel("Kết quả tìm kiếm")
        results_heading.setObjectName("sectionTitle")
        results_tools.addWidget(results_heading)
        self.result_search = QLineEdit()
        self.result_search.setPlaceholderText("Lọc kết quả theo tác giả hoặc nội dung…")
        self.open_post_button = QPushButton("Mở bài gốc")
        self.open_post_button.setToolTip("Mở bài Facebook đang chọn để đối chiếu trước khi duyệt bình luận.")
        self.open_post_button.setEnabled(False)
        self.select_all_button = QPushButton("Chọn bản nháp đang hiện")
        self.clear_selection_button = QPushButton("Bỏ chọn")
        self.reply_comments_button = QPushButton("Trả lời bình luận đã chọn")
        self.reply_comments_button.setEnabled(False)
        self.reply_comments_button.clicked.connect(self.reply_selected_comments)
        self.post_comments_button = QPushButton("Bình luận vào bài đã chọn")
        self.post_comments_button.setEnabled(False)
        self.post_comments_button.clicked.connect(self.comment_selected_posts)
        self.selection_count = QLabel("0 bài đã chọn")
        self.selection_count.setObjectName("countBadge")
        results_tools.addWidget(self.result_search)
        results_tools.addWidget(self.open_post_button)
        results_tools.addWidget(self.select_all_button)
        results_tools.addWidget(self.clear_selection_button)
        results_tools.addWidget(self.reply_comments_button)
        results_tools.addWidget(self.post_comments_button)
        results_tools.addWidget(self.selection_count)
        self.layout.addLayout(results_tools)

        self.results = BaseTable()
        self.results.setColumnCount(9)
        self.results.setHorizontalHeaderLabels(
            ["Chọn", "Tác giả", "Nội dung bài / bình luận", "Liên kết", "Trạng thái", "Quy tắc khớp", "Bình luận dự kiến — sửa bằng bấm đúp", "Mã hàng khớp trong công ty", "Ngày đăng (UTC+7)"]
        )
        self.results.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for column, width in ((0, 50), (1, 120), (2, 280), (3, 220), (4, 150), (5, 230), (6, 340)):
            self.results.setColumnWidth(column, width)
        self.results.setColumnHidden(3, True)
        self.results.setColumnWidth(7, 260)
        self.results.setColumnWidth(8, 160)
        self.results.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.results.setWordWrap(True)
        self.results.verticalHeader().setDefaultSectionSize(100)
        self.results.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.results.itemChanged.connect(self._update_comment_button)
        self.results.itemSelectionChanged.connect(self._update_source_button)
        self.open_post_button.clicked.connect(self.open_source_post)
        self.result_search.textChanged.connect(self._filter_results)
        self.select_all_button.clicked.connect(self._select_unsent)
        self.clear_selection_button.clicked.connect(self._clear_selection)
        self.set_content(self.results)

        self.scan_button, self.comment_button, self.refresh_button = (
            self.toolbar.buttons
        )
        self.ai_button = self.toolbar.add_button("✨ Gợi ý AI", self.suggest_reply)
        self.ai_button.setToolTip(
            "Gửi nội dung bài viết đã chọn tới OpenAI để tạo gợi ý; bạn sẽ xem và sửa trước khi gửi."
        )
        self.ai_button.setEnabled(False)
        self.batch_ai_button = self.toolbar.add_button("✨ AI nhiều bài", self.suggest_batch_replies)
        self.batch_ai_button.setToolTip("Tạo bình luận riêng cho tối đa 10 bài qua OpenAI, sau đó xem và sửa trước khi lưu.")
        self.batch_ai_button.setEnabled(False)
        self.stop_ai_button = self.toolbar.add_button("Dừng gợi ý AI", self.stop_ai)
        self.stop_ai_button.setEnabled(False)
        self.comment_button.setEnabled(False)
        auxiliary = [
            self.toolbar.add_button("⚙ Quy tắc trả lời", self.edit_rules),
            self.toolbar.add_button("🧪 Thử tình huống mẫu", self.show_sample_posts),
            self.toolbar.add_button("Xuất bản nháp CSV", self.export_preview),
            self.toolbar.add_button("Danh mục công ty", self.show_catalog),
        ]
        self.catalog_sample_button = self.toolbar.add_button("Thử sản phẩm công ty", self.show_catalog_samples)
        self.catalog_sample_button.setEnabled(self.catalog is not None)
        auxiliary.append(self.catalog_sample_button)
        self.tools_menu = QMenu(self)
        menu_actions = []
        for button in auxiliary:
            button.hide()
            action = self.tools_menu.addAction(button.text())
            action.triggered.connect(button.click)
            menu_actions.append((action, button))
        self.tools_menu.aboutToShow.connect(lambda: [action.setEnabled(button.isEnabled()) for action, button in menu_actions])
        tools_button = self.toolbar.add_button("Công cụ", None)
        tools_button.setMenu(self.tools_menu)
        self.stop_scan_button = self.toolbar.add_button("Dừng tác vụ", self.stop_scan)
        self.stop_scan_button.setEnabled(False)
        self.stop_scan_button.hide()
        self.stop_ai_button.hide()
        self.pause_scan_button = self.toolbar.add_button("Tạm dừng tác vụ", self.toggle_scan_pause)
        self.pause_ai_button = self.toolbar.add_button("Tạm dừng AI", self.toggle_ai_pause)
        for button in (self.pause_scan_button, self.pause_ai_button):
            button.hide()
            button.setToolTip("Tạm dừng sau thao tác hiện tại, giữ kết quả để tiếp tục.")

        signals.facebook_login.connect(self.refresh_sources)
        signals.buying_posts_found.connect(self._show_posts)
        signals.buying_posts_error.connect(self._show_error)
        signals.comment_result.connect(self._show_comment_result)
        signals.facebook_task_status.connect(self._task_status)
        signals.buying_posts_progress.connect(self._scan_progress, Qt.QueuedConnection)
        signals.groups_synced.connect(self._groups_updated)
        signals.groups_sync_cancelled.connect(lambda profile: self._groups_updated(profile, 0))

        self.refresh_sources()
        self.account_combo.currentIndexChanged.connect(self._refresh_group_sources)
        if self._rule_load_error:
            self.status_label.setText(self._rule_load_error)

    def refresh_sources(self, *_args):
        current_profile = self.account_combo.currentData()
        self.account_combo.clear()
        for account in AccountService().get_all():
            session = browser_pool.get_session(account.profile)
            worker = browser_pool.get_worker(account.profile)
            if session and session.running and session.logged_in and worker:
                label = self.profile_labels.get_label(account.profile)
                self.account_combo.addItem(
                    f"{account.name} · {label}", account.profile
                )

        index = self.account_combo.findData(current_profile)
        if index >= 0:
            self.account_combo.setCurrentIndex(index)
        self._refresh_group_sources()

        has_account = self.account_combo.count() > 0
        self.scan_button.setEnabled(has_account and not self._scan_active)
        if not has_account:
            self.status_label.setText(
                "Chưa có nick đăng nhập. Bạn vẫn có thể bấm Thử tình huống mẫu để duyệt offline."
            )

    def _refresh_group_sources(self, *_args):
        current = self.source_combo.currentData()
        self.source_combo.clear()
        profile = self.account_combo.currentData()
        groups = GroupService().get_for_profile(profile) if profile else []
        self.source_combo.addItem(f"Tất cả nhóm của nick ({len(groups)} nhóm)", "__all_groups__")
        for group in groups:
            self.source_combo.addItem(group.name or group.url, group.url)
        if profile:
            for entry in PublishingService().list_collections(profile):
                self.source_combo.addItem(f"Bộ sưu tập · {entry['name']} ({len(entry['urls'])} nhóm)",
                                          f"__collection__:{entry['id']}")
        index = self.source_combo.findData(current)
        if index >= 0:
            self.source_combo.setCurrentIndex(index)

    def _groups_updated(self, profile, _count):
        if profile == self.account_combo.currentData() and not self._scan_active:
            self._refresh_group_sources()

    def _set_scanning(self, active):
        self._scan_active = active
        for button in self.toolbar.buttons:
            button.setEnabled(not active)
        self.stop_scan_button.setEnabled(active)
        self.stop_scan_button.setVisible(active)
        self.pause_scan_button.setVisible(active)
        self.pause_scan_button.setEnabled(active)
        if not active:
            self.pause_scan_button.setText("Tạm dừng tác vụ")
        self.stop_ai_button.setEnabled(self._suggestion_thread is not None)
        self.scan_button.setEnabled(not active and self.account_combo.count() > 0)
        self.catalog_sample_button.setEnabled(not active and self.catalog is not None)
        for widget in (self.account_combo, self.source_combo, self.phrases_input,
                       self.max_posts_input, self.business_context_input, self.comment_input, self.scan_comments_checkbox):
            widget.setEnabled(not active)
        self.min_ad_comments_input.setEnabled(not active and self.scan_comments_checkbox.isChecked())
        self.catalog_checkbox.setEnabled(not active and self.catalog is not None)
        self.products_input.setEnabled(not active and not self.catalog_checkbox.isChecked())
        self.results.setEditTriggers(
            QAbstractItemView.NoEditTriggers if active else QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        self._update_comment_button()

    def stop_scan(self):
        worker = browser_pool.get_worker(self._pending_profile)
        if worker and self._scan_active:
            self._scan_control.stop()
            worker.scan_cancel_event.set()
            self.stop_scan_button.setEnabled(False)
            self.pause_scan_button.setEnabled(False)
            self.status_label.setText("Đang dừng tác vụ; giữ các kết quả đã có và giữ profile mở...")

    def toggle_scan_pause(self):
        if not self._scan_active or self._scan_control.stopped:
            return
        if self._scan_control.paused:
            self._scan_control.resume()
            self.pause_scan_button.setText("Tạm dừng tác vụ")
            self.status_label.setText("Đã tiếp tục tác vụ từ vị trí đang xử lý.")
        else:
            self._scan_control.pause()
            self.pause_scan_button.setText("Tiếp tục tác vụ")
            self.status_label.setText("Đã yêu cầu tạm dừng sau thao tác hiện tại. Kết quả đang có được giữ nguyên.")

    def toggle_ai_pause(self):
        if self._suggestion_thread is None or self._ai_control.stopped:
            return
        if self._ai_control.paused:
            self._ai_control.resume()
            self.pause_ai_button.setText("Tạm dừng AI")
            self.status_label.setText("Đã tiếp tục gợi ý AI.")
        else:
            self._ai_control.pause()
            self.pause_ai_button.setText("Tiếp tục AI")
            self.status_label.setText("Đã yêu cầu tạm dừng AI. Yêu cầu đang gửi sẽ hoàn tất; giữ kết quả và chờ bạn tiếp tục.")

    def stop_ai(self):
        self._ai_control.stop()
        self._ai_cancel.set()
        self.stop_ai_button.setEnabled(False)
        self.pause_ai_button.setEnabled(False)
        self.status_label.setText("Đang dừng gợi ý AI sau yêu cầu hiện tại; giữ các kết quả đã hoàn tất.")

    @Slot(str, object)
    def _scan_progress(self, profile, progress):
        if profile != self._pending_profile:
            return
        if self._scan_control.paused and progress.get("stage") != "summary":
            return
        if progress.get("stage") == "summary":
            state = {"cancelled": "Đã dừng", "post_limit": "Đạt số bài đã đặt", "completed": "Đã kết thúc", "no_relevant_groups": "Không có nhóm phù hợp sản phẩm"}.get(progress.get("reason"), "Đã kết thúc")
            self.status_label.setText(
                f"{state}: {progress.get('groups_scanned', 0)}/{progress.get('groups_total', 0)} nhóm, "
                f"bỏ {progress.get('groups_skipped_unrelated', 0)} nhóm có tên không liên quan; "
                f"đã đọc {progress.get('seen_posts', 0)} bài; "
                f"{progress.get('found_total', 0)} kết quả từ bài viết và bình luận trong 15 ngày. "
                f"Đã đọc bình luận của {progress.get('comment_sources_read', 0)} bài, {progress.get('comment_errors', 0)} lỗi đọc bình luận. "
                f"Đã loại {progress.get('skipped_ads', 0)} bài quảng cáo. "
                f"Bỏ {progress.get('skipped_old', 0)} bài cũ, {progress.get('skipped_unknown_date', 0)} bài chưa rõ ngày; "
                f"{progress.get('skipped_irrelevant', 0)} bài không khớp nhu cầu/sản phẩm, "
                f"{progress.get('skipped_no_body', 0)} bài chưa đọc được nội dung, {progress.get('extraction_errors', 0)} lỗi đọc bài. "
                f"{progress.get('failed_groups', 0)} nhóm lỗi, {progress.get('limited_groups', 0)} nhóm chạm giới hạn quét. "
                f"Đã lưu {progress.get('saved_posts', 0)} hồ sơ vào Customers; {progress.get('save_errors', 0)} bài lỗi lưu. Chưa gửi bình luận."
            )
        elif progress.get('stage') == 'group_filter':
            self.status_label.setText(
                f"Lọc tên nhóm: giữ {progress.get('groups_total', 0)}/{progress.get('groups_requested', 0)} nhóm liên quan sản phẩm; "
                f"bỏ {progress.get('groups_skipped_unrelated', 0)} nhóm. Đang chuẩn bị quét..."
            )
        elif progress.get("stage") == "group_error":
            self.status_label.setText(f"Không đọc được nhóm {progress.get('group_name', '')}: {progress.get('error', '')}. Đang tiếp tục nhóm khác...")
        else:
            self.status_label.setText(
                f"Nhóm {progress.get('group_index', 0)}/{progress.get('groups_total', 0)} · {progress.get('group_name', '')} · "
                f"lượt {progress.get('scrolls', 0)}, đã đọc {progress.get('seen_posts', 0)} bài, "
                f"tìm được {progress.get('found_total', 0)} kết quả trong 15 ngày; đã đọc bình luận của {progress.get('comment_sources_read', 0)} bài. "
                f"Đã loại {progress.get('skipped_ads', 0)} bài quảng cáo. "
                f"Bỏ {progress.get('skipped_old', 0)} bài cũ, {progress.get('skipped_unknown_date', 0)} bài chưa rõ ngày; "
                f"{progress.get('skipped_irrelevant', 0)} bài không khớp, {progress.get('skipped_no_body', 0)} bài chưa đọc được nội dung, "
                f"{progress.get('extraction_errors', 0)} lỗi đọc bài."
            )

    def _products(self):
        return [word.strip() for word in self.products_input.text().split(",") if word.strip()]

    def _active_catalog(self):
        return self.catalog if self.catalog_checkbox.isChecked() else None

    def _update_catalog_info(self):
        self.catalog_checkbox.setEnabled(self.catalog is not None)
        self.products_input.setEnabled(not self.catalog_checkbox.isChecked())
        if self.catalog is None:
            self.catalog_checkbox.setText("Chưa nạp danh mục; mở Danh mục công ty để nhập Excel.")
            return
        self.catalog_checkbox.setText(
            f"Dùng danh mục công ty: {len(self.catalog.products):,} mặt hàng / {len(self.catalog.categories)} nhóm"
        )
        source = self.catalog.source
        self.catalog_checkbox.setToolTip(
            f"Nguồn: {source.get('filename', '')}\nNgày trong tên tệp: {source.get('snapshot_date_from_filename') or 'Không rõ'}\n"
            "Tồn kho là số trong tệp nhập, không phải tồn kho trực tiếp. Bình luận chỉ mời inbox để kiểm tra."
        )

    def show_catalog_samples(self):
        if self.catalog is None:
            return
        self.catalog_checkbox.setChecked(True)
        self._pending_profile = "__company_samples__"
        self._show_posts(self._pending_profile, catalog_sample_posts(self.catalog))
        self.status_label.setText("Đã tạo câu hỏi mẫu từ hàng hóa công ty. Chưa gửi bình luận; mã hết tồn, hàng mẫu và trường hợp mơ hồ được đánh dấu để duyệt.")

    def show_catalog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Danh mục hàng hóa công ty")
        dialog.resize(1100, 650)
        layout = QVBoxLayout(dialog)
        summary = QLabel()
        summary.setWordWrap(True)
        layout.addWidget(summary)
        search = QLineEdit()
        search.setPlaceholderText("Tìm mã, tên hàng, nhóm hoặc thương hiệu — hỗ trợ không dấu")
        layout.addWidget(search)
        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(["Mã hàng", "Tên hàng", "Nhóm", "Thương hiệu", "Tồn theo tệp", "Loại hàng"])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setColumnWidth(0, 190)
        table.setColumnWidth(1, 430)
        table.setColumnWidth(2, 140)
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table)

        def filter_rows(text):
            query = normalize_text(text)
            for row in range(table.rowCount()):
                table.setRowHidden(row, bool(query) and query not in normalize_text(" ".join(table.item(row, column).text() for column in range(4))))

        def fill():
            products = self.catalog.products if self.catalog else []
            table.setSortingEnabled(False)
            table.setRowCount(len(products))
            for row, product in enumerate(products):
                for column, field in enumerate(("sku", "name", "category", "brand", "stock_snapshot", "item_type")):
                    value = product.get(field)
                    cell = QTableWidgetItem("Chưa rõ" if value is None else str(value))
                    cell.setToolTip(f"{product['source_sheet']} · dòng {product['source_row']}\n{product['name']}")
                    table.setItem(row, column, cell)
            table.setSortingEnabled(True)
            summary.setText(
                f"{len(products):,} mặt hàng. Tồn kho chỉ là số tại thời điểm xuất tệp; không dùng để tự cam kết hàng sẵn.\n"
                + (self.catalog.source.get("filename", "") if self.catalog else "Chọn Nạp Excel để nhập danh mục.")
            )
            filter_rows(search.text())

        def import_file():
            filename, _ = QFileDialog.getOpenFileName(dialog, "Nạp danh sách hàng hóa", "", "Excel (*.xlsx)")
            if not filename:
                return
            try:
                import_catalog(filename)
                self.catalog = load_company_catalog()
            except (ValueError, OSError, KeyError) as exc:
                QMessageBox.warning(dialog, "Không nhập được danh mục", str(exc))
                return
            self.catalog_checkbox.setChecked(True)
            self._update_catalog_info()
            self.catalog_sample_button.setEnabled(True)
            fill()
            self.status_label.setText("Đã nạp danh mục mới. Bấm Thử sản phẩm công ty để tạo lại bản nháp.")

        search.textChanged.connect(filter_rows)
        load = QPushButton("Nạp Excel")
        load.clicked.connect(import_file)
        layout.addWidget(load)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(dialog.reject)
        layout.addWidget(close)
        fill()
        dialog.exec()

    def show_sample_posts(self):
        self._pending_profile = "__samples__"
        self._show_posts(self._pending_profile, sample_posts())
        self.status_label.setText("Đã nạp tình huống mẫu offline. Bấm đúp bình luận dự kiến để sửa; chưa gửi gì lên Facebook.")

    def scan_posts(self):
        if self._suggestion_thread is not None:
            QMessageBox.information(self, "AI đang chạy", "Đợi lượt gợi ý AI kết thúc trước khi tìm bài mới.")
            return
        profile = self.account_combo.currentData()
        source_url = self.source_combo.currentData()
        worker = browser_pool.get_worker(profile) if profile else None
        session = browser_pool.get_session(profile) if profile else None
        phrases = [
            phrase.strip()
            for phrase in self.phrases_input.toPlainText().replace("\n", ",").split(",")
            if phrase.strip()
        ]
        phrases = list(dict.fromkeys(phrases + scan_keywords(self.rules)))

        if not worker or not (session and session.running and session.logged_in):
            QMessageBox.warning(
                self,
                "Chưa chọn tài khoản",
                "Chọn một profile đang đăng nhập để duyệt Facebook.",
            )
            return
        if worker.operation_active:
            QMessageBox.information(self, "Nick đang bận", "Đợi tác vụ đang chạy kết thúc trước khi tìm bài.")
            return
        available = [group.url for group in GroupService().get_for_profile(profile)]
        if source_url == "__all_groups__":
            source_urls = available
        elif str(source_url).startswith("__collection__:"):
            entry = next((x for x in PublishingService().list_collections(profile)
                          if str(x['id']) == source_url.split(':', 1)[1]), None)
            source_urls = [url for url in (entry['urls'] if entry else []) if url in available]
        else:
            source_urls = [source_url]
        if not source_urls:
            QMessageBox.information(self, "Chưa có nhóm", "Vào Groups và bấm Quét nhóm nick đang mở trước khi tìm bài.")
            return
        if not source_url or not phrases or (not self._products() and not self._active_catalog()):
            QMessageBox.warning(
                self,
                "Thiếu thông tin",
                "Chọn nguồn bài viết, từ khóa và ít nhất một sản phẩm quan tâm.",
            )
            return

        self._pending_profile = profile
        self._scan_control = TaskControl()
        self.result_search.clear()
        self.results.setRowCount(0)
        self._update_comment_button()
        self.status_label.setText(f"Đang lọc tên {len(source_urls)} nhóm theo sản phẩm trước khi quét bài trong 15 ngày gần nhất...")
        self._set_scanning(True)
        worker.scan_requested.emit(
            {
                "source_urls": source_urls,
                "task_control": self._scan_control,
                "phrases": phrases,
                "max_posts": self.max_posts_input.value(),
                "max_age_days": 15,
                "scroll_count": 120,
                "seconds_per_group": 180,
                "include_comments": self.scan_comments_checkbox.isChecked(),
                "min_ad_comments": self.min_ad_comments_input.value(),
                "rules": copy.deepcopy(self.rules),
                "products": self._products(),
                "use_catalog": self._active_catalog() is not None,
            }
        )

    def _show_posts(self, profile, posts):
        if profile != self._pending_profile:
            return
        selected_urls = {post["url"] for post in self._selected_posts()}
        manual_comments = {}
        for row in range(self.results.rowCount()):
            selection = self.results.item(row, 0)
            comment = self.results.item(row, 6)
            if not selection or not comment:
                continue
            previous = selection.data(Qt.UserRole)
            if (isinstance(previous, dict)
                    and previous.get("status") in {"draft", "manual_review"}
                    and comment.text() != previous.get("comment", "")):
                key = (previous.get("url"), previous.get("message"),
                       previous.get("published_at"), previous.get("published_until"))
                manual_comments[key] = comment.text()

        was_sorting = self.results.isSortingEnabled()
        self.results.setSortingEnabled(False)
        self.results.blockSignals(True)
        previews = preview_comments(posts, self.rules, self._products(), self._active_catalog())
        self.results.setColumnHidden(7, self._active_catalog() is None)
        self.results.setRowCount(len(previews))
        for row, post in enumerate(previews):
            key = (post.get("url"), post.get("message"),
                   post.get("published_at"), post.get("published_until"))
            selection = QTableWidgetItem("")
            selection.setFlags(
                (selection.flags() & ~Qt.ItemIsEditable)
                | Qt.ItemIsUserCheckable
                | Qt.ItemIsEnabled
                | Qt.ItemIsSelectable
            )
            selection.setCheckState(Qt.Checked if post.get("url") in selected_urls and post["status"] in {"draft", "manual_review"} else Qt.Unchecked)
            selection.setData(Qt.UserRole, post)
            if post["status"] not in {"draft", "manual_review"}:
                selection.setFlags(selection.flags() & ~Qt.ItemIsUserCheckable)
            self.results.setItem(row, 0, selection)

            for column, value in (
                (1, post.get("author", "Facebook user")),
                (2, post.get("message", "")),
                (3, post.get("url", "")),
                (4, ("Trả lời bình luận · " if post.get("target_type") == "comment" else "") + {"draft": "Bản nháp chờ duyệt", "manual_review": "Cần duyệt thủ công", "skipped": "Bỏ qua", "duplicate": "Trùng bài"}[post["status"]]),
                (5, post["rule_name"] + (" · " + ", ".join(post["matched_keywords"]) if post["matched_keywords"] else "")),
                (6, manual_comments.get(key, post["comment"]) if post["status"] in {"draft", "manual_review"} else post["comment"]),
                (7, ", ".join(item["sku"] for item in post.get("catalog_match", {}).get("candidates", [])[:5])
                    or ("Mã chưa có trong danh mục" if post.get("catalog_match", {}).get("kind") == "unknown_model" else "")),
                (8, post.get("published_display") or ("Mẫu offline" if post.get("url", "").startswith("sample://") else "Chưa rõ")),
            ):
                item = QTableWidgetItem(str(value))
                if column != 6 or post["status"] not in {"draft", "manual_review"}:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setToolTip(f"{value}\n{post.get('url', '')}\nBài gốc: {post.get('parent_message', '')}" if column == 2 else str(value) if column == 6 else post["reason"])
                self.results.setItem(row, column, item)

        self.results.blockSignals(False)
        self.results.setSortingEnabled(was_sorting)
        self._filter_results(self.result_search.text())
        self._update_source_button()
        self.scan_button.setEnabled(self.account_combo.count() > 0 and not self._scan_active)
        self._update_comment_button()
        self.status_label.setText(
            f"Đã xem {len(previews)} bài; {sum(post['status'] == 'draft' for post in previews)} bản nháp, "
            f"{sum(post['status'] == 'manual_review' for post in previews)} cần duyệt thủ công. Chưa gửi bình luận."
        )

    def _update_comment_button(self, _item=None):
        selected = self._selected_posts()
        has_checked = bool(selected)
        self.comment_button.setEnabled(has_checked and not self._scan_active)
        self.ai_button.setEnabled(len(selected) == 1 and self._suggestion_thread is None and not self._scan_active)
        self.batch_ai_button.setEnabled(1 <= len(selected) <= 10 and self._suggestion_thread is None and not self._scan_active)
        self.selection_count.setText(f"{len(selected)} bài đã chọn")
        self.reply_comments_button.setEnabled(
            1 <= len(selected) <= 10 and not self._scan_active and self._suggestion_thread is None
            and all(post.get('target_type') == 'comment' and real_post_url(post.get('url'))
                    and post.get('draft_comment', '').strip() and not post.get('reply_sent')
                    for post in selected))
        self.post_comments_button.setEnabled(
            1 <= len(selected) <= 10 and not self._scan_active and self._suggestion_thread is None
            and all(post.get('target_type', 'post') == 'post' and real_post_url(post.get('url'))
                    and post.get('draft_comment', '').strip() and not post.get('reply_sent')
                    for post in selected))

    def reply_selected_comments(self):
        self._review_selected_targets('comment')

    def comment_selected_posts(self):
        self._review_selected_targets('post')

    def _review_selected_targets(self, target_type):
        posts = self._selected_posts()
        if (self._scan_active or self._suggestion_thread is not None or not 1 <= len(posts) <= 10
                or any(post.get('target_type', 'post') != target_type or not real_post_url(post.get('url'))
                       or not post.get('draft_comment', '').strip() or post.get('reply_sent') for post in posts)):
            return
        profile = self._pending_profile
        worker = browser_pool.get_worker(profile)
        session = browser_pool.get_session(profile)
        if not worker or not (session and session.running and session.logged_in) or worker.operation_active:
            QMessageBox.information(self, 'Chưa sẵn sàng', 'Mở đúng profile đã tìm khách và đợi tác vụ đang chạy hoàn tất.')
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('Duyệt bình luận vào bài' if target_type == 'post' else 'Duyệt trả lời bình luận')
        dialog.resize(960, 480)
        layout = QVBoxLayout(dialog)
        destination = 'bài viết' if target_type == 'post' else 'bình luận'
        layout.addWidget(QLabel(f'Gửi bằng profile {profile}. Mỗi nội dung sẽ gửi vào {destination} tương ứng.'))
        table = QTableWidget(len(posts), 3)
        table.setHorizontalHeaderLabels(['Khách / bình luận gốc', 'Bài gốc', 'Trả lời sẽ gửi — có thể sửa'])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setWordWrap(True)
        table.verticalHeader().setDefaultSectionSize(110)
        for row, post in enumerate(posts):
            for column, value in enumerate((f"{post.get('author', '')}: {post.get('message', '')}",
                                           post['url'], self.comment_input.toPlainText().strip() or post['draft_comment'])):
                item = QTableWidgetItem(value)
                item.setToolTip(post['url'])
                if column != 2:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(row, column, item)
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(f'Gửi {len(posts)} trả lời')
        buttons.button(QDialogButtonBox.Cancel).setText('Hủy')
        def accept():
            if all(table.item(row, 2).text().strip() for row in range(len(posts))):
                dialog.accept()
        buttons.accepted.connect(accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        reviewed = [dict(post, draft_comment=table.item(row, 2).text().strip()) for row, post in enumerate(posts)]
        for row in range(self.results.rowCount()):
            item = self.results.item(row, 0)
            if item and item.data(Qt.UserRole):
                match = next((post for post in reviewed if post['url'] == item.data(Qt.UserRole).get('url')), None)
                if match:
                    self.results.item(row, 6).setText(match['draft_comment'])
        self._scan_control = TaskControl()
        self._set_scanning(True)
        self.status_label.setText(f'Đang gửi {len(reviewed)} bình luận đã duyệt...')
        sender = worker.post_comments_requested if target_type == 'post' else worker.comment_replies_requested
        sender.emit(dict(posts=reviewed, reviewed=True, task_control=self._scan_control))

    def _current_post_url(self):
        row = self.results.currentRow()
        item = self.results.item(row, 3) if row >= 0 else None
        return real_post_url(item.text()) if item else None

    def _update_source_button(self):
        self.open_post_button.setEnabled(bool(self._current_post_url()))

    def open_source_post(self):
        url = self._current_post_url()
        if not url:
            self.status_label.setText("Chọn một bài Facebook thật để mở bài gốc; bài mẫu offline không có liên kết.")
            return
        if not QDesktopServices.openUrl(QUrl(url)):
            QMessageBox.warning(self, "Không mở được bài gốc", "Không mở được liên kết Facebook trong trình duyệt.")

    def _filter_results(self, text):
        query = normalize_text(text)
        for row in range(self.results.rowCount()):
            author = self.results.item(row, 1).text() if self.results.item(row, 1) else ""
            message = self.results.item(row, 2).text() if self.results.item(row, 2) else ""
            self.results.setRowHidden(
                row, bool(query) and query not in normalize_text(f"{author} {message}")
            )

    def _select_unsent(self):
        self.results.blockSignals(True)
        for row in range(self.results.rowCount()):
            selection = self.results.item(row, 0)
            if (not self.results.isRowHidden(row) and selection
                    and selection.data(Qt.UserRole).get("status") in {"draft", "manual_review"}):
                selection.setCheckState(Qt.Checked)
        self.results.blockSignals(False)
        self._update_comment_button()

    def _clear_selection(self):
        self.results.blockSignals(True)
        for row in range(self.results.rowCount()):
            selection = self.results.item(row, 0)
            if selection:
                selection.setCheckState(Qt.Unchecked)
        self.results.blockSignals(False)
        self._update_comment_button()

    def _selected_posts(self):
        posts = []
        for row in range(self.results.rowCount()):
            item = self.results.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                post = item.data(Qt.UserRole)
                if post:
                    posts.append(dict(post, draft_comment=self.results.item(row, 6).text()))
        return posts

    def suggest_reply(self):
        if self._suggestion_thread is not None:
            return
        posts = self._selected_posts()
        if len(posts) != 1:
            QMessageBox.information(
                self, "Chọn một bài viết", "Hãy chọn đúng một bài để tạo gợi ý trả lời."
            )
            return

        post = posts[0]
        if not post.get("message", "").strip():
            QMessageBox.information(
                self, "Bài viết trống", "Bài viết này không có nội dung để AI tham khảo."
            )
            return

        thread = QThread(self)
        self._ai_cancel = threading.Event()
        self._ai_control = TaskControl()
        worker = ReplySuggestionWorker()
        worker.moveToThread(thread)
        thread.started.connect(
            lambda: worker.requested.emit(
                {
                    "message": post.get("message", ""),
                    "post": post,
                    "author": post.get("author", ""),
                    "business_context": self.business_context_input.text().strip(),
                    "task_control": self._ai_control,
                    "cancel_event": self._ai_cancel,
                }
            )
        )
        worker.completed.connect(self._apply_reply_suggestions)
        worker.failed.connect(self._show_suggestion_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._suggestion_finished)
        self._suggestion_thread = thread
        self.ai_button.setEnabled(False)
        self.batch_ai_button.setEnabled(False)
        for button in (self.stop_ai_button, self.pause_ai_button):
            button.show()
            button.setEnabled(True)
        self.pause_ai_button.setText("Tạm dừng AI")
        self.status_label.setText("Đang tạo gợi ý trả lời; nội dung chưa được gửi...")
        thread.start()

    def suggest_batch_replies(self):
        if self._suggestion_thread is not None or self._scan_active:
            return
        posts = copy.deepcopy(self._selected_posts())
        if not 1 <= len(posts) <= 10:
            QMessageBox.information(self, "Chọn bài", "Chọn từ 1 đến 10 bài để tạo bình luận riêng cho từng bài.")
            return
        self._ai_cancel = threading.Event()
        self._ai_control = TaskControl()
        request = dict(posts=posts, business_context=self.business_context_input.text().strip(),
                       cancel_event=self._ai_cancel, task_control=self._ai_control)
        thread = QThread(self)
        worker = ReplySuggestionWorker()
        worker.moveToThread(thread)
        thread.started.connect(lambda: worker.requested.emit(request))
        worker.completed.connect(self._review_batch_replies)
        worker.failed.connect(self._show_suggestion_error)
        worker.progress.connect(self._batch_ai_progress)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._suggestion_finished)
        self._suggestion_thread = thread
        self.ai_button.setEnabled(False)
        self.batch_ai_button.setEnabled(False)
        self.stop_ai_button.setEnabled(True)
        self.stop_ai_button.show()
        self.pause_ai_button.show()
        self.pause_ai_button.setEnabled(True)
        self.pause_ai_button.setText("Tạm dừng AI")
        self.status_label.setText(f"Đang tạo bình luận riêng cho {len(posts)} bài…")
        thread.start()

    def _batch_ai_progress(self, done, total):
        if self._ai_control.paused or self._ai_control.stopped:
            return
        self.status_label.setText(f"AI đã xử lý {done}/{total} bài. Chưa lưu hay gửi bình luận.")

    def _review_batch_replies(self, results):
        if not results:
            self.status_label.setText("Đã dừng gợi ý AI; không có bản nháp mới.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Duyệt bình luận AI theo từng bài")
        dialog.resize(950, 540)
        layout = QVBoxLayout(dialog)
        hint = QLabel("Bấm đúp để sửa bình luận. Áp dụng chỉ cập nhật bảng Comment; bấm Lưu bản nháp đã chọn để lưu vào Customers.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        table = QTableWidget(len(results), 3)
        table.setHorizontalHeaderLabels(["Bài viết", "Bình luận AI — có thể sửa", "Kết quả"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setWordWrap(True)
        table.verticalHeader().setDefaultSectionSize(110)
        for row, result in enumerate(results):
            for column, value in enumerate((result['post'].get('message', ''),
                                            next(iter(result['suggestions']), ''), result['error'] or 'Chờ bạn duyệt')):
                item = QTableWidgetItem(value)
                if column != 1 or result['error']:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(row, column, item)
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Áp dụng vào bảng Comment")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        applied = 0
        for index, result in enumerate(results):
            text = table.item(index, 1).text().strip()
            if result['error'] or not text:
                continue
            original = result['post']
            for row in range(self.results.rowCount()):
                post = self.results.item(row, 0).data(Qt.UserRole)
                current = self.results.item(row, 6)
                if (post.get('url') == original.get('url') and post.get('message') == original.get('message')
                        and current.text() == original.get('draft_comment')):
                    current.setText(text)
                    applied += 1
                    break
        self.status_label.setText(f"Đã áp dụng {applied}/{len(results)} bình luận. Giữ nguyên bài đã sửa trong lúc AI chạy và bài gặp lỗi. Chưa gửi bình luận.")

    def edit_rules(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Quy tắc trả lời — chỉ tạo bản nháp")
        dialog.resize(1050, 620)
        layout = QVBoxLayout(dialog)
        hint = QLabel(
            "Quy tắc đầu tiên khớp sẽ được dùng. Từ khóa cách nhau bằng dấu phẩy; "
            "mẫu trả lời hỗ trợ {san_pham}. Ô Cần ý định mua tránh khớp nhầm từ rộng như 'cũ', 'dưới'. "
            "Mẫu có khẳng định hàng sẵn cần được bạn kiểm tra trước khi duyệt."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels(["Tên tình huống", "Từ khóa (khớp một cụm)", "Bình luận mẫu", "Duyệt thủ công", "Cần ý định mua"])
        table.horizontalHeader().setStretchLastSection(True)
        table.setColumnWidth(0, 180)
        table.setColumnWidth(1, 250)
        table.setColumnWidth(2, 360)
        table.verticalHeader().setDefaultSectionSize(85)
        table.setWordWrap(True)
        layout.addWidget(table)

        def fill(items):
            table.setRowCount(len(items))
            for row, item in enumerate(items):
                for column, text in enumerate((item["name"], ", ".join(item["keywords"]), item["reply"])):
                    cell = QTableWidgetItem(text)
                    if column == 0:
                        cell.setData(Qt.UserRole, item["id"])
                    table.setItem(row, column, cell)
                for column, field in ((3, "manual"), (4, "needs_intent")):
                    cell = QTableWidgetItem()
                    cell.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
                    cell.setCheckState(Qt.Checked if item.get(field) else Qt.Unchecked)
                    table.setItem(row, column, cell)

        def collect():
            return [dict(
                id=table.item(row, 0).data(Qt.UserRole), name=table.item(row, 0).text().strip(),
                keywords=[word.strip() for word in table.item(row, 1).text().split(",") if word.strip()],
                reply=table.item(row, 2).text().strip(),
                manual=table.item(row, 3).checkState() == Qt.Checked,
                needs_intent=table.item(row, 4).checkState() == Qt.Checked,
            ) for row in range(table.rowCount())]

        fill(self.rules)
        actions = FlowLayout()
        add = QPushButton("Thêm quy tắc")
        remove = QPushButton("Xóa dòng chọn")
        up = QPushButton("Ưu tiên cao hơn ↑")
        down = QPushButton("Ưu tiên thấp hơn ↓")
        restore = QPushButton("Nạp mặc định")
        for button in (add, remove, up, down, restore):
            actions.addWidget(button)
        layout.addLayout(actions)

        def add_row():
            items = collect()
            items.append(dict(id=f"custom-{uuid.uuid4().hex}", name="Tình huống mới", keywords=["từ khóa mới"],
                              reply="Bác ib em thông tin {san_pham} nhé.", manual=False, needs_intent=False))
            fill(items)
            table.setCurrentCell(table.rowCount() - 1, 0)

        def move(direction):
            row = table.currentRow()
            target = row + direction
            if row >= 0 and 0 <= target < table.rowCount():
                items = collect()
                items[row], items[target] = items[target], items[row]
                fill(items)
                table.setCurrentCell(target, 0)

        add.clicked.connect(add_row)
        remove.clicked.connect(lambda: table.removeRow(table.currentRow()) if table.currentRow() >= 0 else None)
        up.clicked.connect(lambda: move(-1))
        down.clicked.connect(lambda: move(1))
        restore.clicked.connect(lambda: fill(copy.deepcopy(DEFAULT_RULES)))
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)

        def save():
            try:
                items = collect()
                self.rule_store.save(items)
            except (ValueError, OSError, TypeError) as exc:
                QMessageBox.warning(dialog, "Không lưu được quy tắc", str(exc))
                return
            self.rules = items
            dialog.accept()

        buttons.accepted.connect(save)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec() == QDialog.Accepted:
            posts = [self.results.item(row, 0).data(Qt.UserRole) for row in range(self.results.rowCount())]
            if posts:
                self._show_posts(self._pending_profile, posts)
            self.status_label.setText("Đã lưu quy tắc và tạo lại bản nháp. Chưa gửi bình luận.")

    def export_preview(self):
        if not self.results.rowCount():
            QMessageBox.information(self, "Chưa có bản nháp", "Quét bài hoặc nạp tình huống mẫu trước.")
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Xuất bản nháp để duyệt", "binh-luan-cho-duyet.csv", "CSV (*.csv)")
        if not filename:
            return
        try:
            with open(filename, "w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Tác giả", "Bài viết", "URL", "Trạng thái", "Quy tắc", "Bình luận dự kiến", "Lý do", "Mã hàng khớp", "Ngày đăng (UTC+7)"])
                for row in range(self.results.rowCount()):
                    post = self.results.item(row, 0).data(Qt.UserRole)
                    values = [self.results.item(row, column).text() for column in (1, 2, 3, 4, 5, 6)] + [post["reason"]]
                    values.append(self.results.item(row, 7).text())
                    values.append(self.results.item(row, 8).text())
                    # Prevent spreadsheet formulas in imported Facebook content.
                    writer.writerow(["'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value for value in values])
        except OSError as exc:
            QMessageBox.warning(self, "Không xuất được bản nháp", str(exc))
            return
        self.status_label.setText("Đã xuất CSV để duyệt. Chưa gửi bình luận lên Facebook.")

    def _apply_reply_suggestions(self, suggestions):
        if self._ai_control.stopped:
            return
        choice, accepted = QInputDialog.getItem(
            self,
            "Chọn gợi ý trả lời",
            "Bạn có thể sửa nội dung sau khi chọn:",
            suggestions,
            0,
            False,
        )
        if accepted:
            self.advanced_toggle.setChecked(True)
            self.comment_input.setPlainText(choice)
            self.comment_input.setFocus()
            self.status_label.setText(
                "Đã điền gợi ý vào ô nội dung thay thế. Bấm Chuẩn bị bài đã chọn để xem bản nháp; chưa gửi thật."
            )

    def _show_suggestion_error(self, message):
        QMessageBox.warning(self, "Không tạo được gợi ý AI", message)
        self.status_label.setText(message)

    def _suggestion_finished(self):
        self._suggestion_thread = None
        self.stop_ai_button.setEnabled(False)
        self.stop_ai_button.hide()
        self.pause_ai_button.hide()
        self.pause_ai_button.setText("Tạm dừng AI")
        if self._ai_control.stopped:
            self.status_label.setText("Đã dừng gợi ý AI. Các bình luận đã áp dụng vẫn được giữ nguyên.")
        self._update_comment_button()

    def comment_selected(self):
        message = self.comment_input.toPlainText().strip()
        prepared = 0
        for row in range(self.results.rowCount()):
            item = self.results.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                if item.data(Qt.UserRole).get("status") not in {"draft", "manual_review"}:
                    continue
                if message:
                    self.results.item(row, 6).setText(message)
                if self.results.item(row, 6).text().strip():
                    prepared += 1
        posts = [post for post in self._selected_posts() if real_post_url(post.get("url"))]
        if posts and self._pending_profile not in {"", "__samples__", "__company_samples__"}:
            try:
                result = LeadService().save_drafts(self._pending_profile, posts, self.rules, self._products(), self._active_catalog())
            except Exception as exc:
                self.status_label.setText(f"Không lưu được bản nháp: {exc}. Nội dung đang sửa vẫn ở bảng; chưa gửi bình luận.")
                return
            self.status_label.setText(
                f"Đã lưu {result['drafts']} bản nháp vào Customers; bỏ qua {result['skipped']} bài mẫu/cũ/không phù hợp, "
                f"{len(result['errors'])} lỗi cập nhật. Chưa gửi; chọn bình luận rồi dùng nút Trả lời bình luận đã chọn để gửi."
            )
        else:
            self.status_label.setText(f"Đã chuẩn bị {prepared} bản nháp mẫu để bạn duyệt; không lưu mẫu vào Customers. Gửi bình luận thật đang khóa.")

    def _show_comment_result(self, profile, result):
        if profile != self._pending_profile:
            return
        for row in range(self.results.rowCount()):
            item = self.results.item(row, 0)
            if item and item.data(Qt.UserRole):
                post = item.data(Qt.UserRole)
                if post.get("url") == result.get("url"):
                    self.results.item(row, 4).setText(
                        "Bản nháp chờ duyệt" if result.get("dry_run") else
                        "Đã gửi" if result.get("success") else result.get("message", "Lỗi")
                    )
                    if result.get("dry_run"):
                        self.results.item(row, 6).setText(result.get("comment", ""))
                    if result.get("success") or result.get("skipped"):
                        post['reply_sent'] = True
                        item.setData(Qt.UserRole, post)
                        item.setCheckState(Qt.Unchecked)
                    break
        self.status_label.setText(result.get("message", "Đã xử lý bình luận."))

    def _show_error(self, profile, message):
        if profile != self._pending_profile:
            return
        self._set_scanning(False)
        QMessageBox.warning(self, "Không thể xử lý", message)
        self.status_label.setText(message)

    def _task_status(self, profile, task, active):
        if profile != self._pending_profile:
            return
        if task == "scan":
            self._set_scanning(active)
        elif task == "comment":
            self._set_scanning(active)
            if not active:
                self.status_label.setText("Đã kết thúc lượt trả lời; xem trạng thái gửi ở từng dòng.")
