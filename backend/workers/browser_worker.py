import threading

from PySide6.QtCore import QObject, QThread, Signal, Slot

from backend.browser.pool import browser_pool
from backend.services.account_service import AccountService
from backend.services.comment_history_service import CommentHistoryService
from backend.services.group_service import GroupService
from backend.services.logger import AppLogger
from backend.services.comment_rules import LIVE_COMMENTS_ENABLED, preview_comments, suggest_comment
from backend.services.product_catalog import load_company_catalog
from backend.services.lead_service import LeadService
from backend.services.publishing_service import PublishingService
from backend.facebook.parsers.group_parser import normalize_group_url
from backend.signals import signals
from backend.utils.task_control import TaskControl, TaskCancellation


class _ScanCancellation(TaskCancellation):
    pass


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
        self.scan_cancel_event = threading.Event()
        self.group_control = TaskControl()
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
            profile = facebook.get_profile(allow_navigation=False)
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
            self._raise_if_cancelled()
            self.operation_active = False
            AppLogger.log("Profile sẵn sàng. Chọn tác vụ trong Groups, Posts hoặc Comment để tiếp tục.")
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
        cancellation = TaskCancellation(self.cancel_event, control=self.group_control)
        groups = facebook.get_groups(cancel_event=cancellation)
        self._raise_if_cancelled()
        AppLogger.log(f"Đã đọc {len(groups)} nhóm của {self.profile_name}; đang lưu dữ liệu...")

        service = GroupService()
        scan_complete = bool(getattr(facebook, "last_group_scan_complete", False))
        expected = getattr(facebook, "last_group_scan_expected", None)
        result = service.sync_discovered_groups(
            self.profile_name, groups, scan_complete=scan_complete, expected=expected
        )
        added = result["added"]
        scan_complete = result["complete"]

        partial_result = None
        if not scan_complete:
            AppLogger.log(
                f"Quét nhóm chưa xác nhận đầy đủ ({result['count']}/{expected if expected is not None else '?'}); giữ lại liên kết nhóm đã lưu."
            )
            partial_result = (result["count"], expected or 0)
        else:
            AppLogger.log(
                f"Đã quét được {len(groups)} nhóm, thêm mới {added} nhóm."
            )
        if self.group_control.stopped:
            signals.groups_sync_cancelled.emit(self.profile_name)
            return added
        signals.groups_synced.emit(self.profile_name, result["count"])
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
        except InterruptedError:
            if self.group_control.stopped:
                signals.groups_sync_cancelled.emit(self.profile_name)
            else:
                signals.groups_sync_failed.emit(self.profile_name, "Đã dừng quét nhóm.")
        except Exception as exc:
            if self.group_control.stopped:
                signals.groups_sync_cancelled.emit(self.profile_name)
            else:
                AppLogger.exception(f"Lỗi quét nhóm {self.profile_name}: {exc}")
                signals.groups_sync_failed.emit(self.profile_name, str(exc))
        finally:
            self.operation_active = False
            self.group_control = TaskControl()

    @Slot(object)
    def publish_posts(self, request):
        targets = list(request.get("targets") or [])
        cancellation = _ScanCancellation(self.cancel_event, request.get("stop_event") or threading.Event(),
                                         control=request.get("task_control"))
        delay = max(0, min(3600, int(request.get("delay_seconds", 0))))
        def finish(outcomes):
            if len(outcomes) == 1 and not outcomes[0].get("target") and targets:
                outcomes = [dict(outcomes[0], target=target.get("url", ""),
                                 kind=target.get("kind", "group")) for target in targets]
            try:
                PublishingService().record(self.profile_name, outcomes, request.get("content", ""))
            except Exception as exc:
                AppLogger.exception(f"Không lưu được lịch sử đăng bài {self.profile_name}: {exc}")
                signals.status.emit("Không lưu được lịch sử đăng bài. Hãy kiểm tra log.")
            signals.post_publish_finished.emit(self.profile_name, outcomes)
        group_count = sum(1 for target in targets if target.get("kind") == "group")
        outcomes = []
        if group_count > 10:
            outcomes.append({
                "success": False,
                "target": "",
                "message": "Mỗi nick chỉ được đăng tối đa 10 nhóm trong một lần.",
            })
            finish(outcomes)
            return
        if self.operation_active:
            outcomes.append({
                "success": False,
                "target": "",
                "message": "Profile đang bận với một thao tác khác.",
            })
            finish(outcomes)
            return

        session = browser_pool.get_session(self.profile_name)
        if not (session and session.running and session.logged_in):
            outcomes.append({
                "success": False,
                "target": "",
                "message": "Profile chưa đăng nhập hoặc đã đóng.",
            })
            finish(outcomes)
            return

        self.operation_active = True
        signals.facebook_task_status.emit(self.profile_name, "publish", True)
        try:
            facebook = browser_pool.get(self.profile_name).facebook
            for index, target in enumerate(targets):
                if index:
                    cancellation.wait(delay)
                if cancellation.is_set():
                    outcomes.extend(dict(success=False, status="skipped", target=item.get("url", ""),
                                         kind=item.get("kind", "group"), message="Đã dừng tác vụ.")
                                    for item in targets[index:])
                    break
                try:
                    result = facebook.publish_post(
                        target_url=target["url"],
                        message=request.get("content", ""),
                        media_paths=request.get("media_paths", []),
                        cancel_event=cancellation,
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
                        "status": "skipped" if cancellation.is_set() else "failed",
                        "target": target.get("url", ""),
                        "kind": target.get("kind", "group"),
                        "message": str(exc),
                    })
                    outcomes.extend(dict(success=False, status="skipped", target=item.get("url", ""),
                                         kind=item.get("kind", "group"), message="Bỏ qua sau lỗi ở đích trước.")
                                    for item in targets[index + 1:])
                    break
        except Exception as exc:
            outcomes.append({
                "success": False,
                "target": "",
                "message": str(exc),
            })
        finally:
            self.operation_active = False
            signals.facebook_task_status.emit(self.profile_name, "publish", False)
            finish(outcomes)

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
        self.scan_cancel_event.clear()
        cancellation = _ScanCancellation(self.cancel_event, self.scan_cancel_event, control=request.get("task_control"))
        signals.facebook_task_status.emit(self.profile_name, "scan", True)
        try:
            session = browser_pool.get_session(self.profile_name)
            if not (session and session.running and session.logged_in):
                raise RuntimeError("Profile chưa đăng nhập hoặc đã đóng. Mở lại trong Accounts trước khi tìm bài.")
            groups = GroupService().get_for_profile(self.profile_name)
            available = {normalize_group_url(group.url): group.name for group in groups}
            requested = request.get("source_urls")
            if requested is None:
                requested = [request["source_url"]] if request.get("source_url") else list(available)
            sources = list(dict.fromkeys(normalize_group_url(url) for url in requested))
            if not sources:
                raise RuntimeError("Nick chưa có nhóm đã đồng bộ. Vào Groups và quét nhóm trước.")
            if any(url not in available for url in sources):
                raise RuntimeError("Nguồn phải là nhóm đã đồng bộ của nick đang chọn. Hãy làm mới danh sách nhóm.")
            AppLogger.log(f"Tìm bài mua hàng trong {len(sources)} nhóm; chỉ lấy bài trong 15 ngày gần nhất.")
            browser = browser_pool.get(self.profile_name)
            facebook = browser.facebook
            message_filter = None
            catalog = load_company_catalog() if request.get("use_catalog") else None
            if request.get("use_catalog") and catalog is None:
                raise RuntimeError("Chưa có danh mục hàng hóa công ty để quét.")
            if "rules" in request:
                message_filter = lambda text: suggest_comment(
                    text, request["rules"], request.get("products"), catalog
                )["status"] in {"draft", "manual_review"}
            posts, errors, scanned, limited_groups = {}, [], 0, 0
            saved_posts, save_errors = 0, 0
            lead_service = None
            limit = max(1, min(int(request.get("max_posts", 100)), 500))
            totals = dict(seen_posts=0, skipped_old=0, skipped_unknown_date=0, skipped_future=0)
            stop_reason = "completed"
            for group_index, source in enumerate(sources, 1):
                if cancellation.is_set():
                    stop_reason = "cancelled"
                    break
                def progress(stats):
                    signals.buying_posts_progress.emit(self.profile_name, dict(
                        stats, stage="reading", group_index=group_index, groups_total=len(sources),
                        group_name=available[source], source_url=source, found_total=len(posts) + stats.get("found", 0),
                    ))
                progress(dict(found=0, seen_posts=0, scrolls=0))
                try:
                    found = facebook.find_buying_posts(
                        source_url=source, phrases=request["phrases"], max_posts=limit - len(posts),
                        cancel_event=cancellation, message_filter=message_filter,
                        scroll_count=request.get("scroll_count", 120), max_age_days=15,
                        max_seconds=request.get("seconds_per_group", 180), group_only=True,
                        progress_callback=progress,
                    )
                    found = [dict(post, source_name=available[source], source_url=source) for post in found]
                    for post in found:
                        posts[post["url"]] = post
                    if found:
                        try:
                            if lead_service is None:
                                lead_service = LeadService()
                            saved = lead_service.capture_scan(self.profile_name, found, request.get("rules"), request.get("products"), catalog)
                            saved_posts += saved["saved"]
                        except Exception as exc:
                            save_errors += len(found)
                            AppLogger.exception(f"Không lưu được khách hàng tiềm năng: {exc}")
                    stats = getattr(facebook, "last_post_scan_stats", {}) or {}
                    if stats.get("reason") in {"time_budget", "max_scrolls"}:
                        limited_groups += 1
                    for key in totals:
                        totals[key] += stats.get(key, 0)
                    scanned += 1
                    signals.buying_posts_found.emit(self.profile_name, list(posts.values()))
                    AppLogger.log(
                        f"Nhóm {group_index}/{len(sources)} · {available[source]}: "
                        f"{len(found)} bài phù hợp; bỏ {stats.get('skipped_old', 0)} bài cũ, "
                        f"{stats.get('skipped_unknown_date', 0)} bài chưa rõ ngày; dừng nhóm: {stats.get('reason', 'xong')}."
                    )
                except Exception as exc:
                    errors.append(source)
                    AppLogger.exception(f"Không quét được nhóm {available[source]}: {exc}")
                    signals.buying_posts_progress.emit(self.profile_name, dict(
                        stage="group_error", group_index=group_index, groups_total=len(sources),
                        group_name=available[source], error=str(exc), found_total=len(posts),
                    ))
                if cancellation.is_set():
                    stop_reason = "cancelled"
                    break
                if len(posts) >= limit:
                    stop_reason = "post_limit"
                    break
            if errors and not scanned and not cancellation.is_set():
                raise RuntimeError("Không đọc được nhóm nào. Kiểm tra quyền truy cập hoặc đăng nhập Facebook; xem logs/app.log để biết chi tiết.")
            result = sorted(posts.values(), key=lambda post: post.get("published_at", ""), reverse=True)
            signals.buying_posts_found.emit(self.profile_name, result)
            signals.buying_posts_progress.emit(self.profile_name, dict(
                totals, stage="summary", reason=stop_reason, groups_scanned=scanned,
                groups_total=len(sources), failed_groups=len(errors), found_total=len(result),
                limited_groups=limited_groups,
                saved_posts=saved_posts, save_errors=save_errors,
            ))
            AppLogger.log(f"Kết thúc lượt tìm: {len(result)} bài trong 15 ngày, {scanned}/{len(sources)} nhóm, {len(errors)} nhóm lỗi; {stop_reason}.")
        except Exception as exc:
            AppLogger.exception(f"Lỗi khi quét bài mua hàng: {exc}")
            signals.buying_posts_error.emit(self.profile_name, str(exc))
        finally:
            self.operation_active = False
            signals.facebook_task_status.emit(self.profile_name, "scan", False)

    @Slot(object)
    def comment_on_posts(self, request):
        # Live sending stays locked until the user has reviewed this feature.
        # Neither request flags nor the UI can bypass this application-level lock.
        if not LIVE_COMMENTS_ENABLED or request.get("dry_run", True):
            for post in preview_comments(
                request.get("posts", []), request.get("rules"), request.get("products"),
                load_company_catalog() if request.get("use_catalog") else None,
            ):
                signals.comment_result.emit(self.profile_name, {
                    **post, "success": False, "dry_run": True,
                    "message": "Chỉ xem trước; chưa gửi bình luận.",
                })
            return
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
