"""Dispatch persisted schedules to the QThread that owns each Facebook profile."""
from PySide6.QtCore import QObject, QTimer, Signal

from backend.browser.pool import browser_pool
from backend.services.outreach_service import OutreachService, timestamp


class OutreachScheduler(QObject):
    changed = Signal()
    error = Signal(str)

    def __init__(self, service=None, pool=None, parent=None, start=True):
        super().__init__(parent)
        self.service = service or OutreachService()
        self.pool = pool or browser_pool
        self.enabled = True
        self.suspended_profiles = set()
        self._ticking = False
        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.tick)
        if start:
            self.timer.start()

    def tick(self):
        if not self.enabled or self._ticking:
            return
        self._ticking = True
        try:
            changed = bool(self.service.recover_stale())
            now = timestamp(self.service.clock())
            for job in self.service.due_jobs():
                if job['status'] != 'queued' or job['next_at'] > now:
                    continue
                if job['profile'] in self.suspended_profiles:
                    continue
                session = self.pool.get_session(job['profile'])
                worker = self.pool.get_worker(job['profile'])
                if not worker or worker.operation_active or not (session and session.running and session.logged_in):
                    continue
                claimed = self.service.claim(job['id'])
                if claimed:
                    try:
                        worker.outreach_requested.emit(dict(job=claimed, service=self.service))
                    except RuntimeError:
                        self.service.finish(claimed['id'], claimed['token'], 'cancelled', 'Profile đã đóng trước khi nhận tác vụ.')
                    changed = True
            if changed:
                self.changed.emit()
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self._ticking = False
