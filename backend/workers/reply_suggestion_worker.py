from PySide6.QtCore import QObject, Signal, Slot

from backend.ai.reply import suggest_replies


class ReplySuggestionWorker(QObject):
    """Run an AI reply request outside the GUI thread."""

    requested = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self):
        super().__init__()
        self.requested.connect(self.suggest)

    @Slot(object)
    def suggest(self, request):
        try:
            replies = suggest_replies(
                request.get("message", ""),
                author=request.get("author", ""),
                business_context=request.get("business_context", ""),
            )
            self.completed.emit(replies)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()
