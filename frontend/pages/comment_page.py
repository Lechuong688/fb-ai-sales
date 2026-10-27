from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QTableWidgetItem,
)

from backend.browser.pool import browser_pool
from backend.services.account_service import AccountService
from backend.services.group_service import GroupService
from backend.services.profile_label_service import ProfileLabelService
from backend.signals import signals
from backend.workers.reply_suggestion_worker import ReplySuggestionWorker
from frontend.pages.base_page import BasePage
from frontend.widgets.base_table import BaseTable


class CommentPage(BasePage):
    """Browse a logged-in profile's feed/groups and review buyer-intent posts."""

    def __init__(self):
        super().__init__(
            title="Tìm khách hàng có nhu cầu mua",
            description=(
                "Quét bài viết trong bảng tin hoặc nhóm, xem lại kết quả, "
                "rồi chọn bài để bình luận."
            ),
            buttons=[
                ("🔍 Tìm bài mua hàng", self.scan_posts),
                ("💬 Bình luận đã chọn", self.comment_selected),
                ("↻ Làm mới nguồn", self.refresh_sources),
            ],
        )
        self.toolbar.set_search_visible(False)
        self.profile_labels = ProfileLabelService()
        self._pending_profile = ""
        self._suggestion_thread = None

        source_layout = QGridLayout()
        source_layout.setHorizontalSpacing(12)
        source_layout.setVerticalSpacing(8)

        self.account_combo = QComboBox()
        self.source_combo = QComboBox()
        source_layout.addWidget(QLabel("Tài khoản Facebook"), 0, 0)
        source_layout.addWidget(self.account_combo, 1, 0)
        source_layout.addWidget(QLabel("Nguồn bài viết"), 0, 1)
        source_layout.addWidget(self.source_combo, 1, 1)
        self.layout.addLayout(source_layout)

        self.phrases_input = QTextEdit()
        self.phrases_input.setMaximumHeight(70)
        self.phrases_input.setPlaceholderText(
            "Cụm từ thể hiện nhu cầu mua, phân cách bằng dấu phẩy"
        )
        self.phrases_input.setPlainText(
            "cần mua, muốn mua, tìm mua, ai bán, có ai bán, mua ở đâu, xin giá"
        )

        self.comment_input = QTextEdit()
        self.comment_input.setMaximumHeight(82)
        self.comment_input.setPlaceholderText(
            "Nhập nội dung bình luận. Bạn sẽ xem và xác nhận trước khi gửi."
        )
        self.business_context_input = QLineEdit()
        self.business_context_input.setPlaceholderText(
            "Thông tin có thể dùng khi trả lời (tên shop, cách liên hệ...)"
        )

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.addRow("Từ khóa mua hàng", self.phrases_input)
        form.addRow("Thông tin cửa hàng cho AI", self.business_context_input)
        form.addRow("Nội dung bình luận", self.comment_input)
        self.layout.addLayout(form)

        self.status_label = QLabel("Chọn tài khoản và nguồn rồi bấm Tìm bài mua hàng.")
        self.status_label.setObjectName("pageDescription")
        self.layout.addWidget(self.status_label)

        results_tools = QHBoxLayout()
        self.result_search = QLineEdit()
        self.result_search.setPlaceholderText("Lọc kết quả theo tác giả hoặc nội dung…")
        self.select_all_button = QPushButton("Chọn bài chưa gửi")
        self.clear_selection_button = QPushButton("Bỏ chọn")
        self.selection_count = QLabel("0 bài đã chọn")
        results_tools.addWidget(self.result_search, 1)
        results_tools.addWidget(self.select_all_button)
        results_tools.addWidget(self.clear_selection_button)
        results_tools.addWidget(self.selection_count)
        self.layout.addLayout(results_tools)

        self.results = BaseTable()
        self.results.setColumnCount(5)
        self.results.setHorizontalHeaderLabels(
            ["Chọn", "Tác giả", "Nội dung bài viết", "Liên kết", "Kết quả"]
        )
        self.results.setColumnWidth(0, 58)
        self.results.setColumnWidth(1, 150)
        self.results.setColumnWidth(3, 240)
        self.results.setColumnWidth(4, 145)
        self.results.setWordWrap(True)
        self.results.verticalHeader().setDefaultSectionSize(60)
        self.results.itemChanged.connect(self._update_comment_button)
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
        self.comment_button.setEnabled(False)

        signals.facebook_login.connect(self.refresh_sources)
        signals.buying_posts_found.connect(self._show_posts)
        signals.buying_posts_error.connect(self._show_error)
        signals.comment_result.connect(self._show_comment_result)
        signals.facebook_task_status.connect(self._task_status)

        self.refresh_sources()

    def refresh_sources(self, *_args):
        self.account_combo.clear()
        for account in AccountService().get_all():
            session = browser_pool.get_session(account.profile)
            worker = browser_pool.get_worker(account.profile)
            if session and session.running and session.logged_in and worker:
                label = self.profile_labels.get_label(account.profile)
                self.account_combo.addItem(
                    f"{account.name} · {label}", account.profile
                )

        self.source_combo.clear()
        self.source_combo.addItem(
            "Bảng tin Facebook", "https://www.facebook.com/"
        )
        for group in GroupService().get_all():
            self.source_combo.addItem(group.name or group.url, group.url)

        has_account = self.account_combo.count() > 0
        self.scan_button.setEnabled(has_account)
        if not has_account:
            self.status_label.setText(
                "Chưa có profile đang đăng nhập. Hãy mở tài khoản trong Accounts trước."
            )

    def scan_posts(self):
        profile = self.account_combo.currentData()
        source_url = self.source_combo.currentData()
        worker = browser_pool.get_worker(profile) if profile else None
        session = browser_pool.get_session(profile) if profile else None
        phrases = [
            phrase.strip()
            for phrase in self.phrases_input.toPlainText().replace("\n", ",").split(",")
            if phrase.strip()
        ]

        if not worker or not (session and session.running and session.logged_in):
            QMessageBox.warning(
                self,
                "Chưa chọn tài khoản",
                "Chọn một profile đang đăng nhập để duyệt Facebook.",
            )
            return
        if not source_url or not phrases:
            QMessageBox.warning(
                self,
                "Thiếu thông tin",
                "Chọn nguồn bài viết và nhập ít nhất một cụm từ mua hàng.",
            )
            return

        self._pending_profile = profile
        self.result_search.clear()
        self.results.setRowCount(0)
        self._update_comment_button()
        self.status_label.setText("Đang duyệt nguồn và lọc bài viết...")
        self.scan_button.setEnabled(False)
        worker.scan_requested.emit(
            {
                "source_url": source_url,
                "phrases": phrases,
                "max_posts": 30,
            }
        )

    def _show_posts(self, profile, posts):
        if profile != self._pending_profile:
            return

        was_sorting = self.results.isSortingEnabled()
        self.results.setSortingEnabled(False)
        self.results.blockSignals(True)
        self.results.setRowCount(len(posts))
        for row, post in enumerate(posts):
            selection = QTableWidgetItem("")
            selection.setFlags(
                (selection.flags() & ~Qt.ItemIsEditable)
                | Qt.ItemIsUserCheckable
                | Qt.ItemIsEnabled
                | Qt.ItemIsSelectable
            )
            selection.setCheckState(Qt.Unchecked)
            selection.setData(Qt.UserRole, post)
            self.results.setItem(row, 0, selection)

            for column, value in (
                (1, post.get("author", "Facebook user")),
                (2, post.get("message", "")),
                (3, post.get("url", "")),
                (4, "Chưa gửi"),
            ):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if column == 2:
                    item.setToolTip(str(value))
                self.results.setItem(row, column, item)

        self.results.blockSignals(False)
        self.results.setSortingEnabled(was_sorting)
        self._filter_results(self.result_search.text())
        self.scan_button.setEnabled(True)
        self._update_comment_button()
        self.status_label.setText(
            f"Tìm thấy {len(posts)} bài có cụm từ thể hiện nhu cầu mua. "
            "Chọn bài phù hợp để chuẩn bị bình luận."
        )

    def _update_comment_button(self, _item=None):
        selected = self._selected_posts()
        has_checked = bool(selected)
        self.comment_button.setEnabled(has_checked)
        self.ai_button.setEnabled(len(selected) == 1 and self._suggestion_thread is None)
        self.selection_count.setText(f"{len(selected)} bài đã chọn")

    def _filter_results(self, text):
        query = text.strip().casefold()
        for row in range(self.results.rowCount()):
            author = self.results.item(row, 1).text() if self.results.item(row, 1) else ""
            message = self.results.item(row, 2).text() if self.results.item(row, 2) else ""
            self.results.setRowHidden(
                row, bool(query) and query not in f"{author} {message}".casefold()
            )

    def _select_unsent(self):
        self.results.blockSignals(True)
        for row in range(self.results.rowCount()):
            selection = self.results.item(row, 0)
            result = self.results.item(row, 4)
            if selection and result and result.text() != "Đã gửi":
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
                    posts.append(post)
        return posts

    def suggest_reply(self):
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
        worker = ReplySuggestionWorker()
        worker.moveToThread(thread)
        thread.started.connect(
            lambda: worker.requested.emit(
                {
                    "message": post.get("message", ""),
                    "author": post.get("author", ""),
                    "business_context": self.business_context_input.text().strip(),
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
        self.status_label.setText("Đang tạo gợi ý trả lời; nội dung chưa được gửi...")
        thread.start()

    def _apply_reply_suggestions(self, suggestions):
        choice, accepted = QInputDialog.getItem(
            self,
            "Chọn gợi ý trả lời",
            "Bạn có thể sửa nội dung sau khi chọn:",
            suggestions,
            0,
            False,
        )
        if accepted:
            self.comment_input.setPlainText(choice)
            self.comment_input.setFocus()
            self.status_label.setText(
                "Đã điền gợi ý vào ô bình luận. Hãy đọc và chỉnh sửa trước khi gửi."
            )

    def _show_suggestion_error(self, message):
        QMessageBox.warning(self, "Không tạo được gợi ý AI", message)
        self.status_label.setText(message)

    def _suggestion_finished(self):
        self._suggestion_thread = None
        self._update_comment_button()

    def comment_selected(self):
        profile = self._pending_profile or self.account_combo.currentData()
        worker = browser_pool.get_worker(profile) if profile else None
        session = browser_pool.get_session(profile) if profile else None
        message = self.comment_input.toPlainText().strip()
        posts = []
        for row in range(self.results.rowCount()):
            item = self.results.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                post = item.data(Qt.UserRole)
                if post:
                    posts.append(post)

        if (
            not worker
            or not (session and session.running and session.logged_in)
            or not posts
            or not message
        ):
            QMessageBox.warning(
                self,
                "Chưa sẵn sàng",
                "Chọn bài viết và nhập nội dung bình luận trước.",
            )
            return

        answer = QMessageBox.question(
            self,
            "Xác nhận bình luận",
            f"Gửi cùng nội dung này đến {len(posts)} bài đã chọn?\n\n{message}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        self._pending_profile = profile
        self.comment_button.setEnabled(False)
        self.status_label.setText("Đang gửi bình luận cho các bài đã chọn...")
        worker.comment_requested.emit({"posts": posts, "text": message})

    def _show_comment_result(self, profile, result):
        if profile != self._pending_profile:
            return
        for row in range(self.results.rowCount()):
            item = self.results.item(row, 0)
            if item and item.data(Qt.UserRole):
                post = item.data(Qt.UserRole)
                if post.get("url") == result.get("url"):
                    self.results.item(row, 4).setText(
                        "Đã gửi" if result.get("success") else result.get("message", "Lỗi")
                    )
                    if result.get("success"):
                        item.setCheckState(Qt.Unchecked)
                    break
        self.status_label.setText(result.get("message", "Đã xử lý bình luận."))

    def _show_error(self, profile, message):
        if profile != self._pending_profile:
            return
        self.scan_button.setEnabled(self.account_combo.count() > 0)
        QMessageBox.warning(self, "Không thể xử lý", message)
        self.status_label.setText(message)

    def _task_status(self, profile, task, active):
        if profile != self._pending_profile:
            return
        if task == "scan":
            self.scan_button.setEnabled(not active)
        elif task == "comment":
            if active:
                self.comment_button.setEnabled(False)
            else:
                self._update_comment_button()
            if not active:
                self.status_label.setText("Đã hoàn tất lượt gửi bình luận.")
