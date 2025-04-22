# generic_pagination.py

from urllib.parse import urljoin
from bs4 import BeautifulSoup
import requests
import re
import time
from typing import List
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from requests.exceptions import RequestException


def safe_request(url, retries=3, timeout=10):
    """Retry-safe request handler."""
    attempt = 0
    while attempt < retries:
        try:
            response = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            return response
        except (RequestException, Exception) as e:
            print(f"[WARN] Error fetching {url}: {e} (Retry {attempt+1}/{retries})")
            attempt += 1
            time.sleep(2)
    return None


def looks_like_static_pagination(url: str) -> bool:
    """Detect if URL has static pagination format."""
    return bool(re.search(r'(page|p)(=|/)(\d+)', url))


def static_pagination_scrape(base_url: str, max_pages: int = 10) -> List[str]:
    """Handle static pagination (e.g., /page/2 or ?page=2)."""
    seen_urls = set()
    article_urls = []
    
    for i in range(1, max_pages + 1):
        new_url = re.sub(r'(page|p)(=|/)(\d+)', f"\\1\\2{i}", base_url)
        if new_url in seen_urls:
            break

        response = safe_request(new_url)
        if not response:
            break

        seen_urls.add(new_url)
        soup = BeautifulSoup(response.text, "html.parser")
        for link in soup.find_all("a", href=True):
            href = urljoin(new_url, link["href"])
            if re.search(r"(20\d{2}|article|news|robot)", href, re.I):
                article_urls.append(href)

    return list(set(article_urls))


def link_based_scrape(base_url: str, max_pages: int = 10) -> List[str]:
    """Handle link-based pagination (clicking on 'Next')."""
    seen_urls = set()
    article_urls = []
    current_url = base_url

    for _ in range(max_pages):
        response = safe_request(current_url)
        if not response:
            break

        soup = BeautifulSoup(response.text, "html.parser")
        for link in soup.find_all("a", href=True):
            href = urljoin(current_url, link["href"])
            if href not in seen_urls and re.search(r"(20\d{2}|article|news|robot)", href, re.I):
                article_urls.append(href)
                seen_urls.add(href)

        # Find the next page link
        next_link = None
        for link in soup.find_all("a", href=True):
            text = link.get_text(strip=True).lower()
            if ("next" in text or text in {">", "»"} or link.get("rel") == ["next"]):
                next_link = urljoin(current_url, link["href"])
                break

        if not next_link or next_link in seen_urls:
            break

        current_url = next_link

    return list(set(article_urls))


def playwright_scrape(start_url: str, max_scrolls: int = 5) -> List[str]:
    """Handle JS-based pagination using Playwright: scroll + 'Load More' button."""
    article_urls = set()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(start_url, timeout=60000)
            page.wait_for_load_state("networkidle")

            for scroll_num in range(max_scrolls):
                print(f"[Scroll] Attempt {scroll_num+1}/{max_scrolls}…")
                
                # Scroll
                page.mouse.wheel(0, 1000)
                page.wait_for_timeout(1500)

                # Try clicking "Load More"
                load_more = page.locator("button:has-text('Load More')")
                if load_more.count() > 0:
                    try:
                        load_more.first.click()
                        page.wait_for_timeout(2000)
                    except PlaywrightTimeoutError:
                        print("[Playwright] Timeout clicking Load More.")
                        break

            # Final HTML parse
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            for link in soup.find_all("a", href=True):
                href = urljoin(start_url, link["href"])
                if re.search(r"(20\d{2}|article|news|robot)", href, re.I):
                    article_urls.add(href)

            browser.close()

    except Exception as e:
        print(f"[Playwright Error] {e}")
        return []

    return list(article_urls)


def scrape_all_article_links(base_url: str, max_pages: int = 10) -> List[str]:
    """Auto-detect pagination type and scrape article URLs."""
    try:
        if looks_like_static_pagination(base_url):
            print("[🧠 Pagination] Detected static pattern")
            return static_pagination_scrape(base_url, max_pages)
        else:
            response = safe_request(base_url)
            if not response:
                return []

            soup = BeautifulSoup(response.text, "html.parser")

            if soup.find("a", text=re.compile("next|more|>|»", re.I)):
                print("[🧠 Pagination] Detected link-based pagination")
                return link_based_scrape(base_url, max_pages)
            else:
                print("[🧠 Pagination] Falling back to Playwright scroll/click")
                return playwright_scrape(base_url, max_scrolls=max_pages)

    except Exception as e:
        print(f"[⚠️ Universal Pagination Error] {e}")
        return []
