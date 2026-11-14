from PySide6.QtCore import QObject, Signal


class AppSignals(QObject):

    # ===== Account =====
    account_added = Signal(object)
    account_updated = Signal(object)
    account_deleted = Signal(int)

    # ===== Facebook =====
    facebook_login = Signal(object)
    groups_synced = Signal(str, int)
    groups_sync_partial = Signal(str, int, int)
    groups_sync_failed = Signal(str, str)
    groups_sync_cancelled = Signal(str)
    post_publish_finished = Signal(str, object)
    facebook_logout = Signal(object)
    facebook_status = Signal(bool)
    browser_status = Signal(bool)
    buying_posts_found = Signal(str, object)
    buying_posts_error = Signal(str, str)
    buying_posts_progress = Signal(str, object)
    leads_changed = Signal()
    comment_result = Signal(str, object)
    facebook_task_status = Signal(str, str, bool)
    outreach_discovered = Signal(str, object)
    outreach_progress = Signal(str, object)
    outreach_finished = Signal(str, object)

    # ===== Dashboard =====
    dashboard_changed = Signal()

    # ===== Logger =====
    log = Signal(str)

    # ===== Status Bar =====
    status = Signal(str)

    # ===== Crawler =====
    crawler_started = Signal(str)
    crawler_finished = Signal(str)
    crawler_progress = Signal(int)

    # ===== Messenger =====
    message_sent = Signal(object)

    # ===== AI =====
    ai_reply = Signal(object)


signals = AppSignals()
