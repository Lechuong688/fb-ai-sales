from threading import RLock

from backend.browser.manager import BrowserManager


class BrowserPool:

    def __init__(self):

        self.instances = {}
        self.workers = {}
        self._lock = RLock()

    def get(self, profile):

        with self._lock:
            if profile not in self.instances:
                self.instances[profile] = BrowserManager()

            return self.instances[profile]

    def get_session(self, profile):
        with self._lock:
            browser = self.instances.get(profile)
            return browser.get_session() if browser else None

    def register_worker(self, profile, worker):
        with self._lock:
            self.workers[profile] = worker

    def unregister_worker(self, profile, worker=None):
        with self._lock:
            current = self.workers.get(profile)
            if current is not None and (worker is None or current is worker):
                self.workers.pop(profile, None)

    def get_worker(self, profile):
        with self._lock:
            return self.workers.get(profile)

    def get_all_sessions(self):

        sessions = []

        with self._lock:
            browsers = list(self.instances.values())

        for browser in browsers:
            session = browser.get_session()
            if session:
                sessions.append(session)

        return sessions

    def close(self, profile):

        with self._lock:
            browser = self.instances.pop(profile, None)

        if browser:
            browser.stop()

    def close_all(self):

        with self._lock:
            browsers = list(self.instances.values())
            self.instances.clear()
            self.workers.clear()

        for browser in browsers:
            browser.stop()

    def exists(self, profile):

        with self._lock:
            return profile in self.instances

browser_pool = BrowserPool()
