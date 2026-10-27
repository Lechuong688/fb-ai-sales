"""Interactive Facebook login for a persistent application browser profile.

Run with ``python -m backend.browser.login --profile KitchenCare``. The
Facebook session is stored under ``data/profiles/<profile>`` and can then be
reused by the desktop application.
"""

import argparse
import sys

from backend.browser.manager import BrowserManager


def _print(message):
    """Print without crashing when the Windows console cannot encode accents."""
    encoding = sys.stdout.encoding or "utf-8"
    safe_message = message.encode(encoding, errors="replace").decode(
        encoding, errors="replace"
    )
    print(safe_message)


def login(profile_name="default", timeout=300):
    """Open Facebook for a profile and wait for a manual login.

    Returns the detected Facebook profile data, or None if login times out.
    The persistent browser context is always closed after this helper exits;
    Playwright saves its session data in the profile directory.
    """
    profile_name = (profile_name or "").strip()
    if not profile_name:
        raise ValueError("Tên profile không được để trống.")
    if timeout <= 0:
        raise ValueError("Thời gian chờ phải lớn hơn 0.")

    manager = BrowserManager()

    try:
        manager.start(profile_name)
        manager.open_url("https://www.facebook.com/")

        _print("Đăng nhập Facebook trong cửa sổ trình duyệt đã mở.")
        _print(f"Profile: {profile_name} (chờ tối đa {timeout} giây)")

        if not manager.facebook.wait_for_login(timeout=timeout):
            _print("Hết thời gian chờ; profile vẫn được giữ để thử lại sau.")
            return None

        profile = manager.facebook.get_profile()
        _print(f"Đã đăng nhập: {profile.get('name') or '(chưa lấy được tên)'}")
        _print(f"UID: {profile.get('uid') or '(chưa lấy được UID)'}")
        return profile
    finally:
        manager.stop()


def main():
    parser = argparse.ArgumentParser(
        description="Interactive Facebook login for an application profile."
    )
    parser.add_argument("--profile", default="default", help="Profile name under data/profiles")
    parser.add_argument("--timeout", type=int, default=300, help="Login wait time in seconds")
    args = parser.parse_args()

    if args.timeout <= 0:
        parser.error("--timeout phải lớn hơn 0")

    login(args.profile, timeout=args.timeout)


if __name__ == "__main__":
    main()
