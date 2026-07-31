from browser.browser import BrowserManager


def login():
    manager = BrowserManager()

    playwright, context = manager.launch()

    page = context.new_page()

    page.goto(
        "https://www.facebook.com",
        wait_until="networkidle",
    )

    print("=" * 60)
    print("Nếu chưa đăng nhập Facebook thì hãy đăng nhập.")
    print("Sau khi vào được trang chủ, nhấn Enter để lưu phiên.")
    print("=" * 60)

    input()

    context.close()
    playwright.stop()


if __name__ == "__main__":
    login()