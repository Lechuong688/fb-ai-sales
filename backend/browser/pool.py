from backend.browser.manager import BrowserManager


class BrowserPool:

    def __init__(self):

        self.instances = {}

    def get(self, profile):

        if profile not in self.instances:

            self.instances[profile] = BrowserManager()

        return self.instances[profile]

    def get_all_sessions(self):

        sessions = []

        for browser in self.instances.values():

            if browser.get_session():

                sessions.append(
                    browser.get_session()
                )

        return sessions

    def close(self, profile):

        if profile in self.instances:

            self.instances[profile].stop()

            del self.instances[profile]

    def close_all(self):

        for browser in self.instances.values():

            browser.stop()

        self.instances.clear()


browser_pool = BrowserPool()