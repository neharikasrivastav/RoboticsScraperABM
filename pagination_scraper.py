from typing import List
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
import re


def normalize_url(url: str) -> str:
    """
    Clean and normalize a URL by removing trailing slashes and fragments.
    """
    return url.split("#")[0].rstrip("/")


def scrape_all_article_links(base_url: str, max_pages: int = 5) -> List[str]:
    """
    Scrape article links from paginated listing pages using relaxed detection.
    
    Detects links that include year-based paths or keywords like "article", "news", or "robot".
    """
    article_links = set()

    for i in range(1, max_pages + 1):
        url = base_url if i == 1 else f"{base_url.rstrip('/')}/page/{i}/"

        try:
            response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
            if response.status_code != 200:
                break

            soup = BeautifulSoup(response.text, "html.parser")
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]

                # Enhanced detection of article links
                if re.search(r"(20\d{2}|article|news|robot)", href, re.I):
                    full_url = normalize_url(urljoin(base_url, href))
                    article_links.add(full_url)

        except Exception as e:
            print(f"[Pagination Scraper Error] Page {i}: {e}")
            break

    return list(article_links)


def get_paginated_urls(base_url: str, max_pages: int = 5) -> List[str]:
    """
    Generate and verify paginated URLs from a blog or article listing page.
    
    Uses strict date-based permalink filtering (e.g., /2023/09/10/).
    """
    urls = []

    for page in range(1, max_pages + 1):
        page_url = f"{base_url.rstrip('/')}/page/{page}/"
        try:
            response = requests.get(page_url, timeout=10)
            if response.status_code != 200:
                break

            soup = BeautifulSoup(response.text, "html.parser")
            article_links = [
                normalize_url(a['href']) for a in soup.find_all("a", href=True)
                if re.search(r'/20\d{2}/\d{2}/\d{2}/', a['href'])  # strict date filter
            ]
            urls.extend(article_links)

        except Exception as e:
            print(f"[WARN] Failed to fetch {page_url}: {e}")
            break

    return list(set(urls))  # remove duplicates
