"""Cooperative task control; safe to call directly from the GUI thread."""
import threading
import time


class TaskControl:
    def __init__(self):
        self._condition = threading.Condition()
        self._paused_at = None
        self._paused_total = 0.0
        self._stopped = False

    @property
    def paused(self):
        with self._condition:
            return self._paused_at is not None

    @property
    def stopped(self):
        with self._condition:
            return self._stopped

    @property
    def paused_seconds(self):
        with self._condition:
            return self._paused_total + (time.monotonic() - self._paused_at if self._paused_at is not None else 0)

    def pause(self):
        with self._condition:
            if not self._stopped and self._paused_at is None:
                self._paused_at = time.monotonic()

    def resume(self):
        with self._condition:
            if self._paused_at is not None:
                self._paused_total += time.monotonic() - self._paused_at
                self._paused_at = None
            self._condition.notify_all()

    def stop(self):
        with self._condition:
            self._stopped = True
            self.resume()

    def checkpoint(self, cancel_events=()):
        with self._condition:
            while self._paused_at is not None and not self._stopped:
                if any(event.is_set() for event in cancel_events):
                    return False
                self._condition.wait(0.1)
            return not self._stopped and not any(event.is_set() for event in cancel_events)


class TaskCancellation:
    """Event-compatible checkpoints, with pause time excluded from task budgets."""
    def __init__(self, *events, control=None):
        self.events = events
        self.control = control or TaskControl()

    def is_set(self):
        return not self.control.checkpoint(self.events)

    @property
    def paused_seconds(self):
        return self.control.paused_seconds

    def active_time(self):
        return time.monotonic() - self.paused_seconds

    def wait(self, seconds):
        deadline = self.active_time() + seconds
        while not self.is_set():
            remaining = deadline - self.active_time()
            if remaining <= 0:
                return False
            # Stop and profile shutdown are checked even during a long pause or delay.
            with self.control._condition:
                self.control._condition.wait(min(0.1, remaining))
        return True
