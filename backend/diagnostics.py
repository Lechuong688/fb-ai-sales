"""Persist Python, Qt and native crash diagnostics for the desktop application."""

import faulthandler
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys


_fault_stream = None


def configure_diagnostics(log_dir=Path("logs")):
    global _fault_stream
    if _fault_stream is not None:
        return
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("fb_ai_sales")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = RotatingFileHandler(
        log_dir / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [%(threadName)s:%(thread)d] %(message)s"
    ))
    logger.addHandler(handler)
    _fault_stream = (log_dir / "faults.log").open("a", encoding="utf-8")
    faulthandler.enable(file=_fault_stream, all_threads=True)
    previous_hook = sys.excepthook

    def report_exception(exc_type, value, traceback):
        logger.critical("Unhandled exception", exc_info=(exc_type, value, traceback))
        previous_hook(exc_type, value, traceback)

    sys.excepthook = report_exception

    from PySide6.QtCore import qInstallMessageHandler

    def report_qt_message(kind, context, message):
        logger.warning("Qt %s: %s (%s:%s)", kind, message, context.file, context.line)

    qInstallMessageHandler(report_qt_message)
    logger.info("Application started; native crash logging enabled")
