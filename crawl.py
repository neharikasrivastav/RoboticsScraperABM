import uuid, requests, re
from urllib.parse import urlparse
from api_management import get_supabase_client
from markdown_io import save_raw_data
from utils_fetch import fetch_html_playwright
from generic_pagination import scrape_all_article_links

def _unique_name(url: str) -> str:
    parsed = urlparse(url)
    slug   = re.sub(r'[^A-Za-z0-9_]+', '_', (parsed.netloc + parsed.path))[:100]
    return f"{uuid.uuid4().hex[:8]}_{slug}"

def crawl_and_extract(
    base_urls,
    model="gpt-4o",
    user_hint="",
    abm_context="",
    max_pages=3,
    use_scroll=False,            # no longer used
    use_browser_fetch=False,     # no longer used
):
    unique_names = []
    all_article_urls = []

    for base_url in base_urls:
        try:
            print(f"[DEBUG] Crawling {base_url} with generic_pagination...")
            urls = scrape_all_article_links(base_url, max_pages=max_pages)
            print(f"[CRAWL] {len(urls)} articles found from {base_url}")
            all_article_urls.extend(urls)
        except Exception as e:
            print(f"[⚠️] Could not scrape {base_url}: {e}")
            all_article_urls.append(base_url)

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    }

    for url in all_article_urls:
        try:
            raw_html = requests.get(url, headers=headers, timeout=10).text
        except Exception as e:
            print(f"[⚠️] Failed to fetch {url}: {e}")
            raw_html = ""

        uid = _unique_name(url)
        save_raw_data(uid, url=url, raw_data=raw_html)
        unique_names.append(uid)

    from pagination import paginate_urls
    paginate_urls(unique_names, model, user_hint, all_article_urls, abm_context)

    return unique_names
