import threading

from PySide6.QtCore import QObject, QThread, Signal, Slot

from backend.browser.pool import browser_pool
from backend.services.account_service import AccountService
from backend.services.comment_history_service import CommentHistoryService
from backend.services.group_service import GroupService
from backend.services.logger import AppLogger
from backend.signals import signals


class BrowserWorker(QObject):
    """Own one Facebook profile for the lifetime of its dedicated QThread."""

    start_requested = Signal(object)
    stop_requested = Signal()
    scan_requested = Signal(object)
    comment_requested = Signal(object)
    tile_requested = Signal(object)
    groups_sync_requested = Signal()
    publish_requested = Signal(object)

    finished = Signal()
    session_stopped = Signal(str)
    ready = Signal(str)
    shutdown_requested = Signal()
    error = Signal(str)
    account_updated = Signal(object)
    groups_synced = Signal(int)

    def __init__(self):
        super().__init__()
        self.cancel_event = threading.Event()
        self.profile_name = ""
        self.account = None
        self.shutting_down = False
        self.operation_active = False
        self.start_requested.connect(self.open_profile)
        self.stop_requested.connect(self.close_profile)
        self.scan_requested.connect(self.scan_buying_posts)
        self.comment_requested.connect(self.comment_on_posts)
        self.tile_requested.connect(self.tile_profile)
        self.groups_sync_requested.connect(self.rescan_groups)
        self.publish_requested.connect(self.publish_posts)
        self.shutdown_requested.connect(self.shutdown_profile)

    def _emit_runtime_status(self):
        sessions = browser_pool.get_all_sessions()
        signals.browser_status.emit(any(s.running for s in sessions))
        signals.facebook_status.emit(
            any(s.running and s.logged_in for s in sessions)
        )

    @Slot(object)
    def open_profile(self, account):
        start_request = account if isinstance(account, dict) else {"account": account}
        account = start_request["account"]
        self.operation_active = True
        self.account = account
        self.profile_name = (account.profile or "").strip()

        try:
            if not self.profile_name:
                raise RuntimeError("Profile không được để trống.")

            AppLogger.log(f"Đang mở Profile: {self.profile_name}")
            browser = browser_pool.get(self.profile_name)
            browser.start(
                self.profile_name,
                window_bounds=start_request.get("window_bounds"),
            )
            browser_pool.get_session(self.profile_name).running = True
            self._emit_runtime_status()
            self._raise_if_cancelled()

            facebook = browser.facebook
            browser.open_url("https://www.facebook.com/")
            self._raise_if_cancelled()
            AppLogger.log(f"Profile {self.profile_name} đã được mở.")
            AppLogger.log("Đang chờ Facebook đăng nhập...")

            if not facebook.wait_for_login(
                timeout=300,
                cancel_event=self.cancel_event,
            ):
                if self.cancel_event.is_set():
                    raise InterruptedError("Đã dừng yêu cầu đăng nhập.")
                raise RuntimeError(
                    "Hết thời gian chờ đăng nhập Facebook (5 phút)."
                )

            self._raise_if_cancelled()
            profile = facebook.get_profile()
            self._raise_if_cancelled()
            uid = (profile.get("uid") or "").strip()
            name = (profile.get("name") or "").strip()

            if not uid.isdigit():
                raise RuntimeError(
                    "Đã đăng nhập Facebook nhưng không lấy được UID hợp lệ."
                )

            self._raise_if_cancelled()
            account.uid = uid
            if name:
                account.name = name
            account.status = "Online"
            AccountService().update(account)
            self.account_updated.emit(account)
            signals.facebook_login.emit(account)
            self._emit_runtime_status()

            AppLogger.log(f"Đã đăng nhập Facebook: {name or uid}")
            added = self._sync_groups()
            self._raise_if_cancelled()
            self.operation_active = False
            self.groups_synced.emit(added)
            self.ready.emit(self.profile_name)
            self.finished.emit()

        except Exception as exc:
            self.operation_active = False
            if browser_pool.exists(self.profile_name):
                browser_pool.close(self.profile_name)
            self._set_account_offline()
            if self.account is not None:
                signals.facebook_logout.emit(self.account)
            self._emit_runtime_status()

            if not self.cancel_event.is_set():
                AppLogger.log(f"Lỗi Browser: {exc}")
                self.error.emit(str(exc))

            self.finished.emit()
            self.session_stopped.emit(self.profile_name)
            if self.shutting_down:
                QThread.currentThread().quit()

    @Slot(object)
    def tile_profile(self, bounds):
        if bounds and browser_pool.exists(self.profile_name):
            browser_pool.get(self.profile_name).set_window_bounds(bounds)

    def _raise_if_cancelled(self):
        if self.cancel_event.is_set():
            raise InterruptedError("Đã dừng profile.")

    def _sync_groups(self):
        AppLogger.log(f"Đang quét tất cả nhóm Facebook của {self.profile_name}...")
        facebook = browser_pool.get(self.profile_name).facebook
        groups = facebook.get_groups(cancel_event=self.cancel_event)
        self._raise_if_cancelled()

        service = GroupService()
        added = 0
        linked_group_ids = set()
        for group in groups:
            try:
                existing = service.repo.get_by_url(group["url"])
                saved_group = service.create(group["name"], group["url"])
                if saved_group:
                    service.link_to_profile(self.profile_name, saved_group.id)
                    linked_group_ids.add(saved_group.id)
                if saved_group and not existing:
                    added += 1
            except Exception as exc:
                AppLogger.log(f"Lỗi lưu nhóm: {exc}")

        scan_complete = bool(getattr(facebook, "last_group_scan_complete", False))
        expected = getattr(facebook, "last_group_scan_expected", None)
        if scan_complete and (linked_group_ids or expected == 0):
            service.sync_profile_groups(self.profile_name, linked_group_ids)
        elif linked_group_ids:
            previous_groups = service.profile_groups.get_groups_for_profile(
                self.profile_name
            )
            merged_ids = linked_group_ids | {group.id for group in previous_groups}
            service.sync_profile_groups(self.profile_name, merged_ids)
        elif not groups:
            AppLogger.log(
                "Không tìm thấy nhóm hợp lệ; giữ nguyên danh sách đã đồng bộ trước đó."
            )

        partial_result = None
        if not scan_complete:
            AppLogger.log(
                f"Quét nhóm chưa xác nhận đầy đủ ({len(groups)}/{expected or '?'}); giữ lại liên kết nhóm đã lưu."
            )
            partial_result = (len(groups), expected or 0)
        else:
            AppLogger.log(
                f"Đã quét được {len(groups)} nhóm, thêm mới {added} nhóm."
            )
        signals.groups_synced.emit(self.profile_name, len(groups))
        if partial_result:
            signals.groups_sync_partial.emit(
                self.profile_name, partial_result[0], partial_result[1]
            )
        return added

    @Slot()
    def rescan_groups(self):
        if self.operation_active:
            signals.groups_sync_failed.emit(
                self.profile_name,
                "Profile đang bận với một thao tác khác.",
            )
            return

        session = browser_pool.get_session(self.profile_name)
        if not (session and session.running and session.logged_in):
            signals.groups_sync_failed.emit(
                self.profile_name,
                "Profile chưa đăng nhập hoặc đã đóng.",
            )
            return

        self.operation_active = True
        try:
            self._sync_groups()
        except Exception as exc:
            AppLogger.log(f"Lỗi quét nhóm {self.profile_name}: {exc}")
            signals.groups_sync_failed.emit(self.profile_name, str(exc))
        finally:
            self.operation_active = False

    @Slot(object)
    def publish_posts(self, request):
        targets = list(request.get("targets") or [])
        group_count = sum(1 for target in targets if target.get("kind") == "group")
        outcomes = []
        if group_count > 10:
            outcomes.append({
                "success": False,
                "target": "",
                "message": "Mỗi nick chỉ được đăng tối đa 10 nhóm trong một lần.",
            })
            signals.post_publish_finished.emit(self.profile_name, outcomes)
            return
        if self.operation_active:
            outcomes.append({
                "success": False,
                "target": "",
                "message": "Profile đang bận với một thao tác khác.",
            })
            signals.post_publish_finished.emit(self.profile_name, outcomes)
            return

        session = browser_pool.get_session(self.profile_name)
        if not (session and session.running and session.logged_in):
            outcomes.append({
                "success": False,
                "target": "",
                "message": "Profile chưa đăng nhập hoặc đã đóng.",
            })
            signals.post_publish_finished.emit(self.profile_name, outcomes)
            return

        self.operation_active = True
        signals.facebook_task_status.emit(self.profile_name, "publish", True)
        try:
            facebook = browser_pool.get(self.profile_name).facebook
            for target in targets:
                if self.cancel_event.is_set():
                    outcomes.append({
                        "success": False,
                        "target": target.get("url", ""),
                        "message": "Đã dừng tác vụ.",
                    })
                    break
                try:
                    result = facebook.publish_post(
                        target_url=target["url"],
                        message=request.get("content", ""),
                        media_paths=request.get("media_paths", []),
                        cancel_event=self.cancel_event,
                    )
                    outcomes.append({
                        "success": True,
                        "target": target["url"],
                        "kind": target.get("kind", "group"),
                        "message": result.get("message", "Đã gửi bài."),
                    })
                except Exception as exc:
                    outcomes.append({
                        "success": False,
                        "target": target.get("url", ""),
                        "kind": target.get("kind", "group"),
                        "message": str(exc),
                    })
        except Exception as exc:
            outcomes.append({
                "success": False,
                "target": "",
                "message": str(exc),
            })
        finally:
            self.operation_active = False
            signals.facebook_task_status.emit(self.profile_name, "publish", False)
            signals.post_publish_finished.emit(self.profile_name, outcomes)

    @Slot()
    def close_profile(self):
        if not self.profile_name or not browser_pool.exists(self.profile_name):
            return

        browser_pool.close(self.profile_name)

        self._set_account_offline()
        if self.account is not None:
            signals.facebook_logout.emit(self.account)
        self._emit_runtime_status()
        self.session_stopped.emit(self.profile_name)

    @Slot(object)
    def scan_buying_posts(self, request):
        if self.operation_active:
            signals.buying_posts_error.emit(
                self.profile_name,
                "Profile đang xử lý một tác vụ khác.",
            )
            return

        self.operation_active = True
        signals.facebook_task_status.emit(self.profile_name, "scan", True)
        try:
            AppLogger.log(
                f"Đang quét bài mua hàng: {request['source_url']}"
            )
            browser = browser_pool.get(self.profile_name)
            posts = browser.facebook.find_buying_posts(
                source_url=request["source_url"],
                phrases=request["phrases"],
                max_posts=request.get("max_posts", 30),
                cancel_event=self.cancel_event,
            )
            if not self.cancel_event.is_set():
                signals.buying_posts_found.emit(self.profile_name, posts)
                AppLogger.log(
                    f"Tìm thấy {len(posts)} bài viết có dấu hiệu mua hàng."
                )
        except Exception as exc:
            AppLogger.log(f"Lỗi khi quét bài mua hàng: {exc}")
            signals.buying_posts_error.emit(self.profile_name, str(exc))
        finally:
            self.operation_active = False
            signals.facebook_task_status.emit(self.profile_name, "scan", False)

    @Slot(object)
    def comment_on_posts(self, request):
        if self.operation_active:
            signals.buying_posts_error.emit(
                self.profile_name,
                "Profile đang xử lý một tác vụ khác.",
            )
            return

        self.operation_active = True
        signals.facebook_task_status.emit(self.profile_name, "comment", True)
        try:
            facebook = browser_pool.get(self.profile_name).facebook
            history = CommentHistoryService()
            for post in request["posts"]:
                if self.cancel_event.is_set():
                    break
                if history.was_sent(self.profile_name, post["url"]):
                    result = {
                        "url": post["url"],
                        "success": False,
                        "skipped": True,
                        "message": "Đã bình luận bài này trước đó; đã bỏ qua.",
                    }
                    signals.comment_result.emit(self.profile_name, result)
                    AppLogger.log("Bỏ qua bài đã bình luận trước đó.")
                    continue
                try:
                    facebook.comment_on_post(post["url"], request["text"])
                    try:
                        history.record(
                            self.profile_name,
                            post["url"],
                            request["text"],
                            "sent",
                        )
                    except Exception as history_error:
                        AppLogger.log(
                            f"Không lưu được lịch sử bình luận: {history_error}"
                        )
                    result = {
                        "url": post["url"],
                        "success": True,
                        "message": "Đã gửi bình luận.",
                    }
                    AppLogger.log("Đã gửi bình luận vào bài viết đã chọn.")
                except Exception as exc:
                    try:
                        history.record(
                            self.profile_name,
                            post["url"],
                            request["text"],
                            "failed",
                            str(exc),
                        )
                    except Exception as history_error:
                        AppLogger.log(
                            f"Không lưu được lịch sử lỗi bình luận: {history_error}"
                        )
                    result = {
                        "url": post["url"],
                        "success": False,
                        "message": str(exc),
                    }
                    AppLogger.log(f"Lỗi gửi bình luận: {exc}")
                signals.comment_result.emit(self.profile_name, result)
                if result["success"]:
                    # Avoid sending comments too rapidly across a batch.
                    self.cancel_event.wait(2)
        except Exception as exc:
            signals.buying_posts_error.emit(self.profile_name, str(exc))
        finally:
            self.operation_active = False
            signals.facebook_task_status.emit(self.profile_name, "comment", False)

    @Slot()
    def shutdown_profile(self):
        self.shutting_down = True
        self.cancel_event.set()
        self.close_profile()
        QThread.currentThread().quit()

    def _set_account_offline(self):
        if self.account is None:
            return
        try:
            self.account.status = "Offline"
            AccountService().update(self.account)
        except Exception as exc:
            AppLogger.log(f"Không cập nhật được trạng thái tài khoản: {exc}")
