import os
from pathlib import Path


def load_local_env(path=Path(".env")):
    """Load simple KEY=VALUE entries without overriding process variables."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


def get_openai_settings():
    load_local_env()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "gpt-6-astra").strip()
    if not api_key:
        raise RuntimeError(
            "Chưa cấu hình OPENAI_API_KEY. Thêm khóa vào .env để dùng gợi ý AI."
        )
    if not model:
        raise RuntimeError("OPENAI_MODEL không được để trống.")
    return api_key, model
