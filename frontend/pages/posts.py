from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStyle,
    QTableWidgetItem,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from backend.services.account_service import AccountService
from backend.services.group_service import GroupService
from backend.services.post_draft_service import PostDraftService
from backend.browser.pool import browser_pool
from backend.services.profile_label_service import ProfileLabelService
from backend.signals import signals
from frontend.pages.base_page import BasePage
from frontend.widgets.base_table import BaseTable


class PostPage(BasePage):
    """Compose, target and save Facebook post drafts for review."""

    def __init__(self):
        super().__init__(
            title="Soạn bài đăng",
            description="Soạn nội dung, thêm ảnh/video, chọn profile và nhóm rồi lưu bản nháp.",
            buttons=[("＋ Bài nháp mới", self.new_draft), ("↻ Làm mới", self.refresh_all)],
        )
        self.toolbar.set_search_visible(False)
        self.draft_service = PostDraftService()
        self.group_service = GroupService()
        self.profile_labels = ProfileLabelService()
        self.current_draft_id = None
        self._loading_targets = False
        self._group_selection = {}
        self._group_refresh_pending = set()
        self._active_group_picker = None
        self._publish_pending = set()
        self._publish_results = []

        editor = QSplitter(Qt.Horizontal)
        editor.setChildrenCollapsible(False)

        compose_panel = QWidget()
        compose_layout = QVBoxLayout(compose_panel)
        compose_layout.setContentsMargins(4, 4, 10, 4)
        content_header = QHBoxLayout()
        content_header.addWidget(QLabel("Nội dung bài viết"))
        content_header.addStretch()
        self.content_count = QLabel("0 ký tự")
        self.content_count.setObjectName("pageDescription")
        content_header.addWidget(self.content_count)
        compose_layout.addLayout(content_header)
        self.content_input = QTextEdit()
        self.content_input.setPlaceholderText(
            "Viết nội dung bài đăng… Bạn có thể xuống dòng và dùng emoji."
        )
        self.content_input.setMaximumHeight(155)
        compose_layout.addWidget(self.content_input, 2)

        media_header = QHBoxLayout()
        media_header.addWidget(QLabel("Ảnh và video"))
        media_header.addStretch()
        self.add_media_button = QPushButton("＋ Thêm ảnh/video")
        self.remove_media_button = QPushButton("Gỡ tệp đã chọn")
        media_header.addWidget(self.add_media_button)
        media_header.addWidget(self.remove_media_button)
        compose_layout.addLayout(media_header)

        self.media_list = QListWidget()
        self.media_list.setObjectName("postMediaFiles")
        self.media_list.setMaximumHeight(105)
        compose_layout.addWidget(self.media_list)
        compose_layout.addWidget(QLabel("Chọn nick và nhóm"))
        target_splitter = QSplitter(Qt.Horizontal)
        target_splitter.setChildrenCollapsible(False)
        target_splitter.setMinimumHeight(250)

        accounts_panel = QWidget()
        accounts_layout = QVBoxLayout(accounts_panel)
        accounts_layout.setContentsMargins(0, 0, 5, 0)
        accounts_header = QHBoxLayout()
        accounts_header.addWidget(QLabel("Nick · Bảng tin"))
        accounts_header.addStretch()
        self.select_all_profiles_button = QPushButton("Tất cả")
        self.clear_profiles_button = QPushButton("Bỏ chọn")
        accounts_header.addWidget(self.select_all_profiles_button)
        accounts_header.addWidget(self.clear_profiles_button)
        accounts_layout.addLayout(accounts_header)
        self.profile_search = QLineEdit()
        self.profile_search.setPlaceholderText("Tìm nick…")
        accounts_layout.addWidget(self.profile_search)
        self.profile_list = QListWidget()
        self.profile_list.setObjectName("postMediaList")
        self.profile_list.setMinimumWidth(190)
        self.profile_list.setMinimumHeight(210)
        accounts_layout.addWidget(self.profile_list)

        groups_panel = QWidget()
        groups_layout = QVBoxLayout(groups_panel)
        groups_layout.setContentsMargins(5, 0, 0, 0)
        groups_header = QHBoxLayout()
        self.groups_header_label = QLabel("Nhóm đăng bài")
        groups_header.addWidget(self.groups_header_label)
        groups_header.addStretch()
        groups_layout.addLayout(groups_header)
        self.group_picker_button = QPushButton("👥  Chọn nhóm Facebook…")
        self.group_picker_button.setMinimumHeight(48)
        self.group_picker_button.clicked.connect(self.open_group_picker)
        groups_layout.addWidget(self.group_picker_button)
        self.group_selection_summary = QLabel(
            "Chọn một nick bên trái để xem và chọn nhóm của nick đó."
        )
        self.group_selection_summary.setWordWrap(True)
        self.group_selection_summary.setObjectName("pageDescription")
        groups_layout.addWidget(self.group_selection_summary)
        groups_layout.addStretch()

        target_splitter.addWidget(accounts_panel)
        target_splitter.addWidget(groups_panel)
        target_splitter.setStretchFactor(0, 2)
        target_splitter.setStretchFactor(1, 3)
        compose_layout.addWidget(target_splitter, 2)

        self.target_summary = QLabel("Chưa chọn đích")
        self.target_summary.setObjectName("pageDescription")
        self.target_summary.setWordWrap(True)
        self.target_summary.setMaximumHeight(42)
        compose_layout.addWidget(self.target_summary)
        target_note = QLabel(
            "Lưu bản nháp chỉ lưu trên máy. Đăng ngay sẽ gửi bài tới các đích đã chọn. "
            "Chưa thấy nhóm? Mở lại nick trong Accounts để đồng bộ."
        )
        target_note.setWordWrap(True)
        target_note.setObjectName("pageDescription")
        compose_layout.addWidget(target_note)

        compose_actions = QHBoxLayout()
        compose_actions.addStretch()
        self.publish_button = QPushButton("Đăng ngay · tối đa 5 nick / 10 nhóm")
        self.publish_button.setObjectName("toolbarButton")
        self.publish_button.setProperty("variant", "primary")
        self.publish_button.setFixedHeight(36)
        compose_actions.addWidget(self.publish_button)
        self.save_button = QPushButton("Lưu bản nháp")
        self.save_button.setObjectName("toolbarButton")
        self.save_button.setProperty("variant", "secondary")
        self.save_button.setFixedHeight(36)
        compose_actions.addWidget(self.save_button)
        compose_layout.addLayout(compose_actions)

        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(10, 4, 4, 4)
        preview_layout.addWidget(QLabel("Xem trước bài viết"))
        self.preview_text = QTextBrowser()
        self.preview_text.setObjectName("postPreviewText")
        self.preview_text.setPlaceholderText("Nội dung xem trước sẽ hiện ở đây.")
        self.preview_text.setOpenExternalLinks(False)
        preview_layout.addWidget(self.preview_text, 2)
        self.preview_media = QLabel("Chưa có ảnh/video")
        self.preview_media.setAlignment(Qt.AlignCenter)
        self.preview_media.setMinimumHeight(130)
        self.preview_media.setMaximumHeight(280)
        self.preview_media.setObjectName("postMediaPreview")
        preview_layout.addWidget(self.preview_media, 1)
        self.preview_targets = QLabel("Đích: chưa chọn")
        self.preview_targets.setWordWrap(True)
        preview_layout.addWidget(self.preview_targets)

        editor.addWidget(compose_panel)
        editor.addWidget(preview_panel)
        editor.setStretchFactor(0, 3)
        editor.setStretchFactor(1, 2)
        editor.setSizes([700, 500])
        editor.setMinimumHeight(500)

        drafts_panel = QWidget()
        drafts_layout = QVBoxLayout(drafts_panel)
        drafts_layout.setContentsMargins(4, 8, 4, 0)
        drafts_header = QHBoxLayout()
        drafts_header.addWidget(QLabel("Bản nháp đã lưu"))
        drafts_header.addStretch()
        self.delete_draft_button = QPushButton("Xóa bản nháp")
        drafts_header.addWidget(self.delete_draft_button)
        drafts_layout.addLayout(drafts_header)
        drafts_hint = QLabel("Bấm đúp vào một dòng để mở và chỉnh sửa bản nháp.")
        drafts_hint.setObjectName("pageDescription")
        drafts_layout.addWidget(drafts_hint)
        self.drafts_table = BaseTable()
        self.drafts_table.setColumnCount(5)
        self.drafts_table.setHorizontalHeaderLabels(
            ["Nội dung", "Profile", "Nhóm", "Media", "Cập nhật"]
        )
        self.drafts_table.setColumnWidth(0, 430)
        self.drafts_table.setColumnWidth(1, 180)
        self.drafts_table.setColumnWidth(2, 180)
        drafts_layout.addWidget(self.drafts_table)

        self.main_splitter = QSplitter(Qt.Vertical)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.addWidget(editor)
        self.main_splitter.addWidget(drafts_panel)
        self.main_splitter.setStretchFactor(0, 5)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([650, 110])
        self.set_content(self.main_splitter)

        self.add_media_button.clicked.connect(self.add_media)
        self.remove_media_button.clicked.connect(self.remove_selected_media)
        self.save_button.clicked.connect(self.save_draft)
        self.publish_button.clicked.connect(self.publish_selected)
        self.delete_draft_button.clicked.connect(self.delete_selected_draft)
        self.content_input.textChanged.connect(self._render_preview)
        self.content_input.textChanged.connect(
            lambda: self.content_count.setText(
                f"{len(self.content_input.toPlainText())} ký tự"
            )
        )
        self.media_list.model().rowsInserted.connect(self._render_preview)
        self.media_list.model().rowsRemoved.connect(self._render_preview)
        self.profile_list.itemChanged.connect(self._profile_changed)
        self.profile_list.currentRowChanged.connect(self._show_groups_for_current_profile)
        self.profile_search.textChanged.connect(self._filter_profiles)
        self.select_all_profiles_button.clicked.connect(
            lambda: self._set_visible_checks(self.profile_list, Qt.Checked)
        )
        self.clear_profiles_button.clicked.connect(
            lambda: self._set_visible_checks(self.profile_list, Qt.Unchecked)
        )
        self.drafts_table.cellDoubleClicked.connect(self.load_selected_draft)
        signals.facebook_login.connect(self._refresh_targets_preserving_selection)
        signals.facebook_logout.connect(self._refresh_targets_preserving_selection)
        signals.groups_synced.connect(self._on_groups_synced)
        signals.groups_sync_partial.connect(self._on_groups_sync_partial)
        signals.groups_sync_failed.connect(self._on_groups_sync_failed)
        signals.post_publish_finished.connect(self._on_publish_finished)
        self._load_targets()
        self.refresh_drafts()
        self._render_preview()

    def _load_targets(self, saved_profiles=None, saved_groups=None):
        selected_profiles = set(saved_profiles or [])
        self._group_selection = {
            profile: set(urls)
            for profile, urls in (saved_groups or {}).items()
        }
        self._loading_targets = True
        self.profile_list.clear()
        for account in AccountService().get_all():
            profile = (account.profile or "").strip()
            if not profile:
                continue
            session = browser_pool.get_session(profile)
            if not (session and session.running and session.logged_in):
                continue
            display_name = self.profile_labels.get_label(profile)
            if display_name == profile:
                display_name = account.name or profile
                if display_name.strip().casefold() in {"trang chủ", "home", "facebook"}:
                    display_name = profile
            account_item = QListWidgetItem(display_name)
            account_item.setData(Qt.UserRole, profile)
            account_item.setToolTip(
                f"Facebook: {account.name or profile}\nProfile: {profile}"
            )
            account_item.setFlags(account_item.flags() | Qt.ItemIsUserCheckable)
            account_item.setCheckState(
                Qt.Checked if profile in selected_profiles else Qt.Unchecked
            )
            self.profile_list.addItem(account_item)
        if not self.profile_list.count():
            empty = QListWidgetItem("Chưa có profile Facebook")
            empty.setFlags(Qt.NoItemFlags)
            self.profile_list.addItem(empty)
        if self.profile_list.count():
            self.profile_list.setCurrentRow(0)
        self._loading_targets = False
        self._show_groups_for_current_profile()
        self._filter_profiles(self.profile_search.text())
        self._update_target_summary()

    def _current_profile(self):
        item = self.profile_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _show_groups_for_current_profile(self, *_args):
        if self._loading_targets:
            return
        profile = self._current_profile()
        if not profile:
            self.groups_header_label.setText("Nhóm đăng bài")
            self.group_picker_button.setText("👥  Chọn nhóm Facebook…")
            self.group_picker_button.setEnabled(False)
            self.group_selection_summary.setText("Chọn một nick bên trái trước.")
            self._update_target_summary()
            return

        session = browser_pool.get_session(profile)
        if not (session and session.running and session.logged_in):
            self.groups_header_label.setText("Nick chưa đăng nhập")
            self.group_picker_button.setText("👥  Nhóm không khả dụng")
            self.group_picker_button.setEnabled(False)
            self.group_selection_summary.setText(
                "Chỉ nick đang đăng nhập mới hiện nhóm để chọn."
            )
            self._update_target_summary()
            return

        available_groups = self.group_service.get_for_profile(profile)
        selected = self._group_selection.get(profile, set())
        names = [
            self.group_service.clean_group_name(group.name, group.url)
            for group in available_groups
            if group.url in selected
        ]
        count = len(names)
        self.groups_header_label.setText("Nhóm Facebook của nick đang chọn")
        self.group_picker_button.setEnabled(bool(available_groups))
        self.group_picker_button.setText(
            f"👥  Chọn nhóm Facebook  ·  {len(available_groups)} nhóm"
        )
        if not available_groups:
            summary = "Nick này chưa có nhóm đã đồng bộ. Mở lại nick trong Accounts để cập nhật."
        elif names:
            shown = ", ".join(names[:3])
            if count > 3:
                shown += f" và {count - 3} nhóm khác"
            summary = f"Đã chọn {count} nhóm: {shown}"
        else:
            summary = "Chưa chọn nhóm. Bấm nút để mở danh sách đầy đủ."
        self.group_selection_summary.setText(summary)
        self._update_target_summary()

    def open_group_picker(self, *_args):
        profile = self._current_profile()
        if not profile or not self._profile_is_logged_in(profile):
            QMessageBox.information(
                self,
                "Chọn nick đang đăng nhập",
                "Hãy chọn một nick đang đăng nhập để xem các nhóm của nick đó.",
            )
            return

        groups = self.group_service.get_for_profile(profile)
        if not groups:
            QMessageBox.information(
                self,
                "Chưa có nhóm",
                "Nick này chưa có nhóm đã đồng bộ. Mở lại nick trong Accounts để cập nhật.",
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Chọn nhóm Facebook")
        dialog.setMinimumSize(620, 520)
        dialog.resize(700, 620)
        layout = QVBoxLayout(dialog)
        heading = QLabel("Chọn các nhóm để đưa vào bản nháp")
        heading.setStyleSheet("font-size: 14pt; font-weight: 700;")
        layout.addWidget(heading)
        profile_item = self.profile_list.currentItem()
        account_label = profile_item.text() if profile_item else profile
        account_label = account_label.split(" · ", 1)[0]
        account_label = QLabel(f"Nick: {account_label}   ·   {len(groups)} nhóm")
        account_label.setObjectName("pageDescription")
        layout.addWidget(account_label)

        search = QLineEdit()
        search.setPlaceholderText("Tìm tên nhóm…")
        layout.addWidget(search)

        actions = QHBoxLayout()
        select_visible = QPushButton("Chọn tất cả đang hiện")
        clear_all = QPushButton("Bỏ chọn hết")
        selected_count = QLabel()
        selected_count.setObjectName("pageDescription")
        actions.addWidget(select_visible)
        actions.addWidget(clear_all)
        actions.addStretch()
        actions.addWidget(selected_count)
        layout.addLayout(actions)

        group_list = QListWidget()
        group_list.setObjectName("postMediaList")
        group_list.setMinimumHeight(340)
        icon = self.style().standardIcon(QStyle.SP_DirIcon)
        existing_selection = set(self._group_selection.get(profile, set()))

        def add_group_rows(items, selected_urls):
            group_list.blockSignals(True)
            group_list.clear()
            for group in items:
                name = self.group_service.clean_group_name(group.name, group.url)
                group_id = group.url.rstrip("/").rsplit("/", 1)[-1]
                item = QListWidgetItem(icon, name)
                item.setData(Qt.UserRole, group.url)
                item.setToolTip(f"ID: {group_id}\n{group.url}")
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(
                    Qt.Checked if group.url in selected_urls else Qt.Unchecked
                )
                group_list.addItem(item)
            group_list.blockSignals(False)

        add_group_rows(groups, existing_selection)
        layout.addWidget(group_list, 1)

        def update_count(*_args):
            count = sum(
                group_list.item(row).checkState() == Qt.Checked
                for row in range(group_list.count())
            )
            selected_count.setText(f"Đã chọn {count} nhóm")

        group_list.itemChanged.connect(update_count)
        search.textChanged.connect(lambda text: self._filter_list(group_list, text))
        select_visible.clicked.connect(
            lambda: self._set_visible_checks(group_list, Qt.Checked)
        )
        clear_all.clicked.connect(
            lambda: self._set_visible_checks(group_list, Qt.Unchecked)
        )
        update_count()

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Save).setText("Lưu lựa chọn")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        refresh_groups = QPushButton("↻ Quét lại nhóm của nick này")
        actions.insertWidget(0, refresh_groups)

        def reload_group_rows():
            selected_urls = {
                group_list.item(row).data(Qt.UserRole)
                for row in range(group_list.count())
                if group_list.item(row).checkState() == Qt.Checked
            }
            latest_groups = self.group_service.get_for_profile(profile)
            account_label.setText(f"Nick: {account_label.text().split('   ·', 1)[0].replace('Nick: ', '')}   ·   {len(latest_groups)} nhóm")
            add_group_rows(latest_groups, selected_urls)
            self._filter_list(group_list, search.text())
            update_count()

        self._active_group_picker = {
            "profile": profile,
            "reload": reload_group_rows,
            "button": refresh_groups,
        }
        refresh_groups.clicked.connect(lambda: self._request_group_refresh(profile))

        if dialog.exec() != QDialog.Accepted:
            self._active_group_picker = None
            return

        self._group_selection[profile] = {
            group_list.item(row).data(Qt.UserRole)
            for row in range(group_list.count())
            if group_list.item(row).checkState() == Qt.Checked
        }
        self._show_groups_for_current_profile()
        self._render_preview()
        self._active_group_picker = None

    def _profile_changed(self, *_args):
        if not self._loading_targets:
            self._update_target_summary()
            self._render_preview()

    @staticmethod
    def _filter_list(widget, query):
        query = query.strip().casefold()
        for index in range(widget.count()):
            item = widget.item(index)
            item.setHidden(bool(query) and query not in item.text().casefold())

    def _filter_profiles(self, query):
        self._filter_list(self.profile_list, query)
        current = self.profile_list.currentItem()
        if current is None or current.isHidden():
            first_visible = next(
                (
                    row
                    for row in range(self.profile_list.count())
                    if not self.profile_list.item(row).isHidden()
                ),
                -1,
            )
            self.profile_list.setCurrentRow(first_visible)

    @staticmethod
    def _set_visible_checks(widget, state):
        for index in range(widget.count()):
            item = widget.item(index)
            if not item.isHidden() and item.flags() & Qt.ItemIsUserCheckable:
                item.setCheckState(state)

    def _selected_targets(self):
        profiles = [
            self.profile_list.item(index).data(Qt.UserRole)
            for index in range(self.profile_list.count())
            if self.profile_list.item(index).checkState() == Qt.Checked
            and self._profile_is_logged_in(
                self.profile_list.item(index).data(Qt.UserRole)
            )
        ]
        visible_profiles = {
            self.profile_list.item(index).data(Qt.UserRole)
            for index in range(self.profile_list.count())
            if self.profile_list.item(index).data(Qt.UserRole)
            and self._profile_is_logged_in(
                self.profile_list.item(index).data(Qt.UserRole)
            )
        }
        groups = {
            profile: sorted(urls)
            for profile, urls in self._group_selection.items()
            if urls and profile in visible_profiles
        }
        return profiles, groups

    @staticmethod
    def _profile_is_logged_in(profile):
        session = browser_pool.get_session(profile) if profile else None
        return bool(session and session.running and session.logged_in)

    def _update_target_summary(self):
        profiles, groups = self._selected_targets()
        group_count = sum(len(urls) for urls in groups.values())
        profile_names = {
            self.profile_list.item(index).data(Qt.UserRole): self.profile_list.item(index).text()
            for index in range(self.profile_list.count())
            if self.profile_list.item(index).data(Qt.UserRole)
        }
        group_details = ", ".join(
            f"{profile_names.get(profile, profile)} ({len(urls)})"
            for profile, urls in groups.items()
            if urls
        )
        summary = f"Feed: {len(profiles)} nick · Nhóm: {group_count}"
        self.target_summary.setText(
            f"{summary}" + (f"\nNhóm theo nick: {group_details}" if group_details else "")
        )
        self.preview_targets.setText(
            f"Đích bản nháp: {summary}"
            + (f"\nNhóm theo nick: {group_details}" if group_details else "")
        )

    def add_media(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Chọn ảnh hoặc video",
            "",
            "Media (*.png *.jpg *.jpeg *.webp *.gif *.mp4 *.mov *.m4v);;Tất cả tệp (*.*)",
        )
        known = {
            self.media_list.item(index).data(Qt.UserRole)
            for index in range(self.media_list.count())
        }
        for path in paths:
            if path not in known:
                item = QListWidgetItem(Path(path).name)
                item.setToolTip(path)
                item.setData(Qt.UserRole, path)
                self.media_list.addItem(item)
        self._render_preview()

    def remove_selected_media(self):
        for item in self.media_list.selectedItems():
            self.media_list.takeItem(self.media_list.row(item))
        self._render_preview()

    def _media_paths(self):
        return [
            self.media_list.item(index).data(Qt.UserRole)
            for index in range(self.media_list.count())
        ]

    def _render_preview(self, *_args):
        self.preview_text.setPlainText(self.content_input.toPlainText())
        paths = self._media_paths()
        if not paths:
            self.preview_media.setPixmap(QPixmap())
            self.preview_media.setText("Chưa có ảnh/video")
            self._update_target_summary()
            return
        first_path = Path(paths[0])
        pixmap = QPixmap(str(first_path)) if first_path.is_file() else QPixmap()
        if not pixmap.isNull():
            self.preview_media.setText("")
            self.preview_media.setPixmap(
                pixmap.scaled(
                    self.preview_media.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )
        else:
            self.preview_media.setPixmap(QPixmap())
            self.preview_media.setText(
                f"{first_path.name}\n+{len(paths) - 1} tệp khác"
                if len(paths) > 1
                else first_path.name
            )
        self._update_target_summary()

    def save_draft(self):
        content = self.content_input.toPlainText().strip()
        media_paths = self._media_paths()
        profiles, groups = self._selected_targets()
        for profile, urls in list(groups.items()):
            valid_urls = {
                group.url for group in self.group_service.get_for_profile(profile)
            }
            groups[profile] = [url for url in urls if url in valid_urls]
            self._group_selection[profile] = set(groups[profile])
        groups = {profile: urls for profile, urls in groups.items() if urls}
        if not content and not media_paths:
            QMessageBox.warning(self, "Thiếu nội dung", "Nhập nội dung hoặc thêm ít nhất một tệp media.")
            return
        if not profiles and not groups:
            QMessageBox.warning(self, "Chưa chọn đích", "Chọn ít nhất một profile hoặc nhóm cho bản nháp.")
            return

        draft = self.draft_service.save(
            self.current_draft_id, content, media_paths, profiles, groups
        )
        self.current_draft_id = draft.id
        self.refresh_drafts()
        QMessageBox.information(
            self, "Đã lưu bản nháp", "Bản nháp đã lưu trên máy để bạn xem lại. Chưa có bài nào được đăng."
        )

    def publish_selected(self):
        content = self.content_input.toPlainText().strip()
        media_paths = self._media_paths()
        if not content and not media_paths:
            QMessageBox.warning(self, "Thiếu nội dung", "Nhập nội dung hoặc thêm ảnh/video trước khi đăng.")
            return

        profiles, groups = self._selected_targets()
        targets_by_profile = {}
        for profile in profiles:
            targets_by_profile.setdefault(profile, []).append({
                "kind": "feed",
                "url": "https://www.facebook.com/",
            })
        for profile, urls in groups.items():
            targets_by_profile.setdefault(profile, []).extend(
                {"kind": "group", "url": url} for url in urls
            )

        group_count = sum(
            1
            for targets in targets_by_profile.values()
            for target in targets
            if target["kind"] == "group"
        )
        over_limit = {
            profile: sum(target.get("kind") == "group" for target in targets)
            for profile, targets in targets_by_profile.items()
        }
        over_limit = {
            profile: count for profile, count in over_limit.items() if count > 10
        }
        if over_limit:
            details = "\n".join(
                f"{profile}: {count} nhóm đã chọn (tối đa 10)"
                for profile, count in over_limit.items()
            )
            QMessageBox.warning(self, "Quá giới hạn nhóm mỗi nick", details)
            return
        if len(targets_by_profile) > 5:
            QMessageBox.warning(
                self,
                "Chọn tối đa 5 nick",
                "Mỗi lần đăng chỉ hỗ trợ tối đa 5 nick đang đăng nhập.",
            )
            return
        if not targets_by_profile:
            QMessageBox.warning(
                self,
                "Chưa chọn đích",
                "Chọn nick để đăng lên bảng tin hoặc chọn nhóm Facebook.",
            )
            return

        workers = {}
        for profile in targets_by_profile:
            worker = browser_pool.get_worker(profile)
            if not worker or not self._profile_is_logged_in(profile):
                QMessageBox.warning(
                    self,
                    "Nick chưa đăng nhập",
                    f"Profile {profile} không còn đăng nhập. Mở lại trong Accounts rồi thử lại.",
                )
                return
            if worker.operation_active:
                QMessageBox.warning(
                    self,
                    "Nick đang bận",
                    f"Profile {profile} đang xử lý tác vụ khác. Hãy đợi xong rồi thử lại.",
                )
                return
            workers[profile] = worker

        feed_count = sum(
            target["kind"] == "feed"
            for targets in targets_by_profile.values()
            for target in targets
        )
        answer = QMessageBox.question(
            self,
            "Xác nhận đăng bài",
            f"Sẽ gửi bài tới {feed_count} bảng tin và {group_count} nhóm Facebook "
            "(tối đa 10 nhóm mỗi nick, 5 nick).\n"
            "Mỗi nhóm có thể cần quản trị viên duyệt bài. Tiếp tục?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        self._publish_results = []
        self._publish_pending = set(targets_by_profile)
        self.publish_button.setEnabled(False)
        self.publish_button.setText("Đang đăng…")
        for profile, targets in targets_by_profile.items():
            workers[profile].publish_requested.emit({
                "content": content,
                "media_paths": media_paths,
                "targets": targets,
            })

    def _on_publish_finished(self, profile, outcomes):
        self._publish_results.extend(
            (profile, outcome) for outcome in (outcomes or [])
        )
        self._publish_pending.discard(profile)
        if self._publish_pending:
            self.publish_button.setText(
                f"Đang đăng… ({len(self._publish_pending)} nick còn lại)"
            )
            return

        self.publish_button.setEnabled(True)
        self.publish_button.setText("Đăng ngay · tối đa 5 nick / 10 nhóm")
        successful = sum(
            bool(outcome.get("success"))
            for _profile, outcome in self._publish_results
        )
        details = []
        for profile_name, outcome in self._publish_results:
            target = outcome.get("target") or ""
            kind = outcome.get("kind", "")
            destination = "Bảng tin" if kind == "feed" else target
            status = "Đã gửi" if outcome.get("success") else "Lỗi"
            details.append(
                f"{status} · {profile_name} · {destination}\n{outcome.get('message', '')}"
            )
        text = f"Đã gửi {successful}/{len(self._publish_results)} đích.\n\n"
        text += "\n\n".join(details)
        if successful:
            QMessageBox.information(self, "Kết quả đăng bài", text)
        else:
            QMessageBox.warning(self, "Không đăng được bài", text)

    def refresh_drafts(self, *_args):
        drafts = self.draft_service.get_all()
        self.drafts_table.setRowCount(len(drafts))
        for row, draft in enumerate(drafts):
            profiles = self.draft_service.decode_list(draft.target_profiles)
            groups = self.draft_service.decode_groups(draft.target_groups)
            group_count = sum(len(urls) for urls in groups.values())
            media = self.draft_service.decode_list(draft.media_paths)
            values = (
                " ".join((draft.content or "").split())[:100] or "(Chỉ có media)",
                str(len(profiles)),
                str(group_count),
                str(len(media)),
                draft.updated_at.strftime("%Y-%m-%d %H:%M") if draft.updated_at else "",
            )
            for column, value in enumerate(values):
                table_item = QTableWidgetItem(value)
                table_item.setData(Qt.UserRole, draft.id)
                table_item.setFlags(table_item.flags() & ~Qt.ItemIsEditable)
                self.drafts_table.setItem(row, column, table_item)

    def load_selected_draft(self, row, _column=0):
        item = self.drafts_table.item(row, 0)
        if not item:
            return
        draft_id = item.data(Qt.UserRole)
        draft = self.draft_service.repo.get(draft_id)
        if not draft:
            return
        self.current_draft_id = draft.id
        self.content_input.setPlainText(draft.content or "")
        self.media_list.clear()
        for path in self.draft_service.decode_list(draft.media_paths):
            media_item = QListWidgetItem(Path(path).name)
            media_item.setToolTip(path)
            media_item.setData(Qt.UserRole, path)
            self.media_list.addItem(media_item)
        self._load_targets(
            self.draft_service.decode_list(draft.target_profiles),
            self.draft_service.decode_groups(draft.target_groups),
        )
        self._render_preview()

    def delete_selected_draft(self):
        row = self.drafts_table.currentRow()
        item = self.drafts_table.item(row, 0) if row >= 0 else None
        if not item:
            QMessageBox.information(self, "Chọn bản nháp", "Chọn một bản nháp cần xóa.")
            return
        answer = QMessageBox.question(
            self,
            "Xóa bản nháp",
            "Bạn có chắc muốn xóa bản nháp đã chọn?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.draft_service.delete(item.data(Qt.UserRole))
        if self.current_draft_id == item.data(Qt.UserRole):
            self.new_draft()
        self.refresh_drafts()

    def new_draft(self):
        self.current_draft_id = None
        self.content_input.clear()
        self.media_list.clear()
        self._load_targets()
        self.drafts_table.clearSelection()
        self._render_preview()

    def refresh_all(self):
        self._refresh_targets_preserving_selection()
        self.refresh_drafts()
        profiles = {
            (account.profile or "").strip()
            for account in AccountService().get_all()
            if (account.profile or "").strip()
            and self._profile_is_logged_in((account.profile or "").strip())
        }
        requested = set()
        for profile in profiles:
            if self._request_group_refresh(profile):
                requested.add(profile)
        self._update_refresh_button()
        if requested:
            signals.status.emit(
                f"Đang quét lại nhóm trên {len(requested)} profile Facebook..."
            )
        elif not profiles:
            signals.status.emit("Không có profile Facebook đang đăng nhập để quét nhóm.")

    def _request_group_refresh(self, profile):
        if profile in self._group_refresh_pending:
            signals.status.emit(f"Đang quét nhóm của {profile}...")
            return False
        worker = browser_pool.get_worker(profile)
        if not worker:
            signals.status.emit(f"Không tìm thấy worker đang chạy cho profile {profile}.")
            return False
        if worker.operation_active:
            signals.status.emit(
                f"Profile {profile} đang bận; hãy đợi tác vụ hiện tại xong rồi quét lại."
            )
            return False
        self._group_refresh_pending.add(profile)
        picker = self._active_group_picker
        if picker and picker["profile"] == profile:
            picker["button"].setEnabled(False)
            picker["button"].setText("⏳ Đang quét nhóm…")
        self._update_refresh_button()
        worker.groups_sync_requested.emit()
        signals.status.emit(f"Đang quét lại nhóm Facebook của {profile}...")
        return True

    def _update_refresh_button(self):
        if not self.toolbar.buttons:
            return
        button = self.toolbar.buttons[1] if len(self.toolbar.buttons) > 1 else self.toolbar.buttons[0]
        if self._group_refresh_pending:
            button.setText(f"⏳ Đang quét nhóm ({len(self._group_refresh_pending)})")
        else:
            button.setText("↻ Làm mới")
            button.setEnabled(True)

    def _on_groups_synced(self, profile, count):
        self._group_refresh_pending.discard(profile)
        self._refresh_targets_preserving_selection()
        self._update_refresh_button()
        picker = self._active_group_picker
        if picker and picker["profile"] == profile:
            picker["reload"]()
            picker["button"].setEnabled(True)
            picker["button"].setText("↻ Quét lại nhóm của nick này")
        if profile:
            signals.status.emit(f"Đã quét và đồng bộ {count} nhóm cho profile {profile}.")

    def _on_groups_sync_failed(self, profile, message):
        self._group_refresh_pending.discard(profile)
        self._update_refresh_button()
        picker = self._active_group_picker
        if picker and picker["profile"] == profile:
            picker["button"].setEnabled(True)
            picker["button"].setText("↻ Quét lại nhóm của nick này")
        signals.status.emit(f"Không quét được nhóm của {profile}: {message}")

    @staticmethod
    def _on_groups_sync_partial(profile, found, expected):
        if expected:
            signals.status.emit(
                f"Facebook mới tải được {found}/{expected} nhóm của {profile}; đã giữ dữ liệu cũ để tránh mất nhóm."
            )
        else:
            signals.status.emit(
                f"Quét nhóm của {profile} chưa xác nhận đầy đủ ({found} thấy được); đã giữ dữ liệu cũ."
            )

    def _refresh_targets_preserving_selection(self, *_args):
        profiles, groups = self._selected_targets()
        self._load_targets(profiles, groups)
