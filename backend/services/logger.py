import logging

from backend.signals import signals


class AppLogger:

    @staticmethod
    def log(message: str):
        logging.getLogger("fb_ai_sales").info(message)
        print(message)
        signals.log.emit(message)

    @staticmethod
    def exception(message: str):
        logging.getLogger("fb_ai_sales").error(message, exc_info=True)
        print(message)
        signals.log.emit(message)
