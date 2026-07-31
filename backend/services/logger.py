class AppLogger:

    _listeners = []

    @classmethod
    def register(cls, callback):

        cls._listeners.append(callback)

    @classmethod
    def log(cls, text):

        print(text)

        for callback in cls._listeners:

            callback(text)