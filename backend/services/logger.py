from backend.signals import signals


class AppLogger:

    @staticmethod
    def log(message: str):
        print(message)
        signals.log.emit(message)