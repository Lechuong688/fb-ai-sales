from PySide6.QtCore import QObject, Signal


class AppSignals(QObject):

    # ===== Account =====
    account_added = Signal(object)
    account_updated = Signal(object)
    account_deleted = Signal(int)

    # ===== Facebook =====
    facebook_login = Signal(object)
    facebook_logout = Signal(object)

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