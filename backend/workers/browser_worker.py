import threading
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QObject, QThread, Signal, Slot

from backend.browser.pool import browser_pool
from backend.browser.outreach import OutreachBrowser, OutreachNeedsReview
from backend.services.account_service import AccountService
from backend.services.comment_history_service import CommentHistoryService
from backend.services.group_service import GroupService
from backend.services.group_relevance import group_search_terms, group_name_matches
from backend.services.logger import AppLogger
from backend.services.comment_rules import LIVE_COMMENTS_ENABLED, preview_comments
from backend.services.product_catalog import load_company_catalog
from backend.services.lead_service import LeadService, real_post_url
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
    comment_replies_requested = Signal(object)
    post_comments_requested = Signal(object)
    tile_requested = Signal(object)
    groups_sync_requested = Signal()
    publish_requested = Signal(object)
    outreach_search_requested = Signal(object)
    outreach_requested = Signal(object)
    outreach_open_requested = Signal(str)

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
        self.outreach_control = TaskControl()
        self.profile_name = ""
        self.account = None
        self.shutting_down = False
        self.operation_active = False
        self.start_requested.connect(self.open_profile)
        self.stop_requested.connect(self.close_profile)
        self.scan_requested.connect(self.scan_buying_posts)
        self.comment_requested.connect(self.comment_on_posts)
        self.comment_replies_requested.connect(self.reply_to_selected_comments)
        self.post_comments_requested.connect(self.comment_on_selected_posts)
        self.tile_requested.connect(self.tile_profile)
        self.groups_sync_requested.connect(self.rescan_groups)
        self.publish_requested.connect(self.publish_posts)
        self.outreach_search_requested.connect(self.discover_outreach)
        self.outreach_requested.connect(self.run_outreach)
        self.outreach_open_requested.connect(self.open_outreach_target)
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
            catalog = load_company_catalog() if request.get("use_catalog") else None
            if request.get("use_catalog") and catalog is None:
                raise RuntimeError("Chưa có danh mục hàng hóa công ty để quét.")
            requested_count = len(sources)
            terms = group_search_terms(request.get('products'), catalog)
            skipped_groups = [url for url in sources if not group_name_matches(available[url], terms)]
            sources = [url for url in sources if group_name_matches(available[url], terms)]
            for url in skipped_groups:
                AppLogger.log(f"Bỏ qua nhóm không liên quan sản phẩm: {available[url] or '(chưa có tên)'} · {url}")
            signals.buying_posts_progress.emit(self.profile_name, dict(
                stage='group_filter', groups_total=len(sources), groups_requested=requested_count,
                groups_skipped_unrelated=len(skipped_groups),
            ))
            AppLogger.log(f"Lọc tên nhóm: giữ {len(sources)}/{requested_count} nhóm liên quan; bỏ {len(skipped_groups)} nhóm. Chỉ lấy bài trong 15 ngày gần nhất.")
            if sources:
                facebook = browser_pool.get(self.profile_name).facebook
            posts, errors, scanned, limited_groups = {}, [], 0, 0
            saved_posts, save_errors = 0, 0
            lead_service = None
            limit = max(1, min(int(request.get("max_posts", 100)), 500))
            totals = dict(seen_posts=0, skipped_old=0, skipped_unknown_date=0, skipped_future=0,
                          skipped_no_body=0, skipped_irrelevant=0, extraction_errors=0,
                          skipped_ads=0,
                          comment_sources_read=0, comment_errors=0)
            stop_reason = "completed" if sources else 'no_relevant_groups'
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
                        cancel_event=cancellation,
                        scroll_count=request.get("scroll_count", 120), max_age_days=15,
                        max_seconds=request.get("seconds_per_group", 180), group_only=True,
                        progress_callback=progress,
                        include_comments=request.get("include_comments", True),
                        min_ad_comments=request.get("min_ad_comments", 10),
                        products=request.get("products"), catalog=catalog, rules=request.get("rules"),
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
                        f"{len(found)} bài phù hợp / {stats.get('seen_posts', 0)} bài đọc được "
                        f"/ {stats.get('seen_cards', 0)} khối hiển thị; "
                        f"{stats.get('skipped_no_body', 0)} bài thiếu nội dung, "
                        f"{stats.get('skipped_irrelevant', 0)} bài không khớp, "
                        f"{stats.get('skipped_ads', 0)} bài quảng cáo bị loại khỏi kết quả; "
                        f"{stats.get('extraction_errors', 0)} lỗi trích xuất; "
                        f"bỏ {stats.get('skipped_old', 0)} bài cũ, "
                        f"{stats.get('skipped_unknown_date', 0)} bài chưa rõ ngày; dừng nhóm: {stats.get('reason', 'xong')}."
                    )
                    if stats.get('last_extraction_error'):
                        AppLogger.log(f"Lỗi đọc bài gần nhất tại {source}: {stats['last_extraction_error']}")
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
                groups_requested=requested_count, groups_skipped_unrelated=len(skipped_groups),
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
        # Bulk post comments stay preview-only. Reviewed comment replies use
        # reply_to_selected_comments and their own review dialog.
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
        self._send_comments(request)

    @Slot(object)
    def comment_on_selected_posts(self, request):
        """Send the exact post drafts reviewed in the dedicated dialog."""
        posts = request.get('posts') or []
        if request.get('reviewed') is not True or not 1 <= len(posts) <= 10:
            signals.buying_posts_error.emit(self.profile_name, 'Duyệt từ 1 đến 10 bình luận trước khi gửi.')
            return
        targets = []
        for post in posts:
            url = real_post_url(post.get('url'))
            query = parse_qs(urlparse(url or '').query)
            if (not url or {'comment_id', 'reply_comment_id'} & query.keys()
                    or post.get('target_type', 'post') != 'post'
                    or not str(post.get('draft_comment') or '').strip()):
                signals.buying_posts_error.emit(self.profile_name, 'Mỗi bình luận cần link bài gốc và nội dung đã duyệt.')
                return
            targets.append(dict(post, url=url))
        session = browser_pool.get_session(self.profile_name)
        if not (session and session.running and session.logged_in):
            signals.buying_posts_error.emit(self.profile_name, 'Profile chưa đăng nhập hoặc đã đóng.')
            return
        self._send_comments(dict(request, posts=targets))

    @Slot(object)
    def reply_to_selected_comments(self, request):
        """Separate reviewed comment replies from the locked bulk-post sender."""
        posts = request.get('posts') or []
        if request.get('reviewed') is not True or not 1 <= len(posts) <= 10:
            signals.buying_posts_error.emit(self.profile_name, 'Duyệt từ 1 đến 10 trả lời trước khi gửi.')
            return
        targets = []
        for post in posts:
            url = real_post_url(post.get('url'))
            query = parse_qs(urlparse(url or '').query)
            if (not url or not query.get('comment_id') or post.get('target_type') != 'comment'
                    or not str(post.get('draft_comment') or '').strip()):
                signals.buying_posts_error.emit(self.profile_name, 'Mỗi trả lời cần đúng link bình luận và nội dung đã duyệt.')
                return
            targets.append(dict(post, url=url))
        session = browser_pool.get_session(self.profile_name)
        if not (session and session.running and session.logged_in):
            signals.buying_posts_error.emit(self.profile_name, 'Profile chưa đăng nhập hoặc đã đóng.')
            return
        self._send_comments(dict(request, posts=targets))

    def _send_comments(self, request):
        if self.operation_active:
            signals.buying_posts_error.emit(
                self.profile_name,
                "Profile đang xử lý một tác vụ khác.",
            )
            return

        self.operation_active = True
        self.scan_cancel_event.clear()
        cancellation = _ScanCancellation(self.cancel_event, self.scan_cancel_event, control=request.get('task_control'))
        signals.facebook_task_status.emit(self.profile_name, "comment", True)
        try:
            facebook = browser_pool.get(self.profile_name).facebook
            history = CommentHistoryService()
            for post in request["posts"]:
                if cancellation.is_set():
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
                    text = post.get("draft_comment") or post.get("comment") or request.get("text", "")
                    facebook.comment_on_post(post["url"], text)
                    try:
                        history.record(
                            self.profile_name,
                            post["url"],
                            text,
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
                            text,
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
                    cancellation.wait(2)
        except Exception as exc:
            signals.buying_posts_error.emit(self.profile_name, str(exc))
        finally:
            self.operation_active = False
            signals.facebook_task_status.emit(self.profile_name, "comment", False)

    @Slot(object)
    def discover_outreach(self, request):
        if self.operation_active:
            signals.outreach_finished.emit(self.profile_name, dict(error='Nick đang xử lý tác vụ khác.'))
            return
        self.operation_active = True
        cancellation = TaskCancellation(self.cancel_event, control=request.get('control') or self.outreach_control)
        signals.facebook_task_status.emit(self.profile_name, 'outreach_search', True)
        try:
            session = browser_pool.get_session(self.profile_name)
            if not (session and session.running and session.logged_in):
                raise RuntimeError('Profile chưa đăng nhập.')
            adapter = OutreachBrowser(browser_pool.get(self.profile_name).facebook)
            results = adapter.discover(request['kind'], request.get('query', ''), request.get('industry', ''),
                request.get('region', ''), request.get('limit', 50), cancel=cancellation,
                progress=lambda value: signals.outreach_progress.emit(self.profile_name, value))
            request['service'].save_targets(self.profile_name, results)
            signals.outreach_discovered.emit(self.profile_name, results)
        except InterruptedError:
            signals.outreach_finished.emit(self.profile_name, dict(message='Đã dừng tìm kiếm. Danh sách đã lưu được giữ nguyên.'))
        except Exception as exc:
            AppLogger.exception(f'Lỗi tìm đối tượng: {exc}')
            signals.outreach_finished.emit(self.profile_name, dict(error=str(exc)))
        finally:
            self.operation_active = False
            signals.facebook_task_status.emit(self.profile_name, 'outreach_search', False)

    @Slot(object)
    def run_outreach(self, request):
        service, job = request['service'], request['job']
        adapter = None
        owns_operation = False
        result = dict(status='failed', message='Không thực hiện được tác vụ.')
        class JobCancellation:
            def is_set(inner):
                return self.cancel_event.is_set() or service.is_cancelled(job['id'], job['token'])
        cancellation = TaskCancellation(JobCancellation(), control=request.get('control'))
        try:
            if self.operation_active:
                raise RuntimeError('Profile đang bận. Lịch chưa thực hiện; hãy tạo lại sau khi kiểm tra.')
            stored = service.running_job(job['id'], job['token'])
            if not stored:
                raise InterruptedError('Lịch không còn ở trạng thái đang chạy.')
            job = stored
            if job['profile'] != self.profile_name or service.is_cancelled(job['id'], job['token']):
                raise InterruptedError('Lịch đã dừng hoặc không thuộc profile này.')
            session = browser_pool.get_session(self.profile_name)
            if not (session and session.running and session.logged_in):
                raise RuntimeError('Profile chưa đăng nhập.')
            self.operation_active = owns_operation = True
            signals.facebook_task_status.emit(self.profile_name, 'outreach', True)
            if job['action'] == 'group_post':
                joined = {normalize_group_url(group.url) for group in GroupService().get_for_profile(self.profile_name)}
                if normalize_group_url(job['target']) not in joined:
                    raise RuntimeError('Nhóm chưa có trong danh sách đã tham gia của nick. Quét lại Groups trước khi đăng.')
            adapter = OutreachBrowser(browser_pool.get(self.profile_name).facebook)
            result = adapter.perform(job, cancellation)
        except InterruptedError as exc:
            result = dict(status='review' if adapter and adapter.mutated else 'cancelled', message=str(exc))
        except OutreachNeedsReview as exc:
            result = dict(status='review', message=str(exc))
        except Exception as exc:
            result = dict(status='review' if adapter and adapter.mutated else 'failed', message=str(exc))
            AppLogger.exception(f'Lỗi lịch kết nối {job["id"]}: {exc}')
        finally:
            try:
                service.finish(job['id'], job['token'], result['status'], result['message'])
            except Exception as exc:
                AppLogger.exception(f'Không lưu được kết quả lịch: {exc}')
                result = dict(status='review', message=f'Không lưu được kết quả, kiểm tra Facebook trước khi chạy lại: {exc}')
            if owns_operation:
                self.operation_active = False
                signals.facebook_task_status.emit(self.profile_name, 'outreach', False)
            signals.outreach_finished.emit(self.profile_name, dict(result, job_id=job['id']))

    @Slot(str)
    def open_outreach_target(self, url):
        if self.operation_active:
            signals.outreach_finished.emit(self.profile_name, dict(error='Profile đang bận, đợi tác vụ kết thúc trước khi mở đích.'))
            return
        try:
            from backend.services.outreach_service import normalize_target
            valid = any(self._valid_outreach_url(kind, url, normalize_target) for kind in ('group', 'person', 'thread', 'post'))
            if not valid:
                raise ValueError('Link đích không hợp lệ.')
            OutreachBrowser(browser_pool.get(self.profile_name).facebook).open(url, self.cancel_event)
        except Exception as exc:
            signals.outreach_finished.emit(self.profile_name, dict(error=str(exc)))

    @staticmethod
    def _valid_outreach_url(kind, url, normalizer):
        try:
            normalizer(kind, url)
            return True
        except ValueError:
            return False

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
