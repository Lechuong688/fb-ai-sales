from PySide6.QtCore import QObject, Signal, Slot

from backend.ai.reply import suggest_replies
from backend.utils.task_control import TaskControl


def reply_context(post):
    if post.get('target_type') == 'comment':
        return (f"Bình luận cần trả lời: {post.get('message', '')[:900]}\n"
                f"Ngữ cảnh bài gốc: {post.get('parent_message', '')[:700]}\n"
                "Hãy trả lời người viết bình luận theo nhu cầu của họ.")
    return post.get('message', '')


class ReplySuggestionWorker(QObject):
    """Run an AI reply request outside the GUI thread."""

    requested = Signal(object)
    completed = Signal(object)
    progress = Signal(int, int)
    failed = Signal(str)
    finished = Signal()

    def __init__(self):
        super().__init__()
        self.requested.connect(self.suggest)

    @Slot(object)
    def suggest(self, request):
        control = request.get('task_control') or TaskControl()
        events = (request['cancel_event'],) if request.get('cancel_event') is not None else ()
        try:
            if "posts" in request:
                posts = request['posts']
                if not 1 <= len(posts) <= 10:
                    raise ValueError("Chọn từ 1 đến 10 bài cho mỗi lượt gợi ý AI.")
                results = []
                for index, post in enumerate(posts):
                    if not control.checkpoint(events):
                        break
                    try:
                        replies = suggest_replies(reply_context(post), author=post.get('author', ''),
                                                  business_context=request.get('business_context', ''))
                        results.append(dict(post=post, suggestions=replies, error=''))
                    except Exception as exc:
                        results.append(dict(post=post, suggestions=[], error=str(exc)))
                    self.progress.emit(index + 1, len(posts))
                control.checkpoint(events)
                self.completed.emit(results)
                return
            if not control.checkpoint(events):
                return
            replies = suggest_replies(
                reply_context(request['post']) if request.get('post') else request.get("message", ""),
                author=request.get("author", ""),
                business_context=request.get("business_context", ""),
            )
            if control.checkpoint(events):
                self.completed.emit(replies)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()
