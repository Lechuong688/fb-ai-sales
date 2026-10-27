import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from backend.config import get_openai_settings


RESPONSES_URL = "https://api.openai.com/v1/responses"


def _extract_output_text(response):
    chunks = []
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                text = content.get("text", "").strip()
                if text:
                    chunks.append(text)
    return "\n".join(chunks).strip()


def _parse_suggestions(text):
    suggestions = []
    for line in text.splitlines():
        cleaned = line.strip().lstrip("-•* ")
        cleaned = cleaned.removeprefix("1.").removeprefix("2.").removeprefix("3.").strip()
        if cleaned:
            suggestions.append(cleaned)
    return suggestions[:3]


def suggest_replies(post_text, author="", business_context=""):
    """Generate editable Vietnamese comment ideas with the Responses API."""
    post_text = (post_text or "").strip()
    if not post_text:
        raise ValueError("Bài viết không có nội dung để tạo gợi ý.")

    api_key, model = get_openai_settings()
    input_text = (
        f"Tác giả bài viết: {author or 'không rõ'}\n"
        f"Thông tin kinh doanh người dùng cung cấp: {business_context or 'không có'}\n"
        f"Nội dung bài viết:\n{post_text[:1800]}"
    )
    payload = {
        "model": model,
        "instructions": (
            "Bạn hỗ trợ nhân viên bán hàng viết phản hồi tiếng Việt cho người đang hỏi mua. "
            "Tạo đúng 3 gợi ý ngắn, lịch sự, tự nhiên, liên quan trực tiếp bài viết. "
            "Không bịa giá, tồn kho, bảo hành, địa chỉ hoặc cam kết. "
            "Không dùng lời gây áp lực. Mỗi gợi ý trên một dòng, không đánh số."
        ),
        "input": input_text,
    }
    request = Request(
        RESPONSES_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=35) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body).get("error", {}).get("message", "")
        except json.JSONDecodeError:
            detail = ""
        raise RuntimeError(detail or f"OpenAI API trả về HTTP {exc.code}.") from exc
    except URLError as exc:
        raise RuntimeError(f"Không kết nối được OpenAI API: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("OpenAI API phản hồi quá thời gian chờ.") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenAI API trả về dữ liệu không hợp lệ.") from exc

    suggestions = _parse_suggestions(_extract_output_text(response_data))
    if not suggestions:
        raise RuntimeError("AI không trả về gợi ý bình luận.")
    return suggestions
