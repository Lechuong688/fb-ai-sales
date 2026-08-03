from backend.browser.manager import BrowserManager

browser = BrowserManager()

page = browser.start()

page.goto("https://facebook.com")

input("Đăng nhập Facebook xong thì nhấn Enter...")

browser.stop()