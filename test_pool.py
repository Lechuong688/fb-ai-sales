from backend.browser.pool import browser_pool

browser = browser_pool.get("KitchenCare")

browser.start("KitchenCare")

print(browser_pool.get_all_sessions())