from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

def scrape_articles_with_load_more(base_url, max_clicks=20):
    article_links = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(base_url, timeout=60000)
            page.wait_for_load_state("networkidle")

            for i in range(max_clicks):
                print(f"[Scroll] Attempt {i+1}/{max_clicks}…")

                # Try clicking a "Load More" button
                load_more = page.locator("button:has-text('Load More'), button:has-text('Show More'), button:has-text('More')")
                if load_more.count() > 0:
                    load_more.first.click()
                    try:
                        page.wait_for_selector("a[href*='202']", timeout=5000)
                    except PlaywrightTimeoutError:
                        print("⚠️ Timeout waiting for new content, breaking.")
                        break
                else:
                    page.mouse.wheel(0, 3000)
                    page.wait_for_timeout(2000)

            # scrape final loaded HTML
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.select("a[href]"):
                href = a["href"].split("?")[0]
                if re.search(r"(202\d|article|robot|news)", href, re.I) and not href.startswith("http"):
                    full_url = urljoin(base_url, href)
                    article_links.add(full_url)

            links = list(article_links)
            print(f"[✅ Scraper] Found {len(links)} article URLs.")
            for l in links[:5]:
                print("   └─", l)

            return links

        except Exception as e:
            print(f"[❌ Error] Failed to load or scrape {base_url}: {e}")
            return []

        finally:
            try:
                browser.close()
            except Exception:
                pass

