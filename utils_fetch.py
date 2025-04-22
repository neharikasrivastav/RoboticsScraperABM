# utils_fetch.py
from playwright.sync_api import sync_playwright, TimeoutError


def fetch_html_playwright(url: str, timeout_ms: int = 30_000) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, timeout=timeout_ms)
            page.wait_for_load_state("networkidle")
            return page.content()
        except TimeoutError:
            print(f"[Playwright] Timeout while loading {url}")
            return ""
        finally:
            browser.close()

