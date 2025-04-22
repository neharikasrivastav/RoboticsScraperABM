import asyncio
import hashlib
from typing import List
from api_management import get_supabase_client
from crawl4ai import AsyncWebCrawler
from markdown_io import save_raw_data
from pagination import paginate_urls

supabase = get_supabase_client()

async def get_fit_markdown_async(url: str) -> str:
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
        return result.markdown if result.success else ""

def fetch_fit_markdown(url: str) -> str:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(get_fit_markdown_async(url))
    finally:
        loop.close()

def fetch_and_store_markdowns(urls: List[str], selected_model="gpt-4o", abm_context="") -> List[str]:
    unique_names = []
    url_name_map = {}

    def normalize_url(url: str) -> str:
        return url.split("#")[0].rstrip("/")

    # Step 1: Fetch initial markdowns and store
    for url in urls:
        url = normalize_url(url)
        try:
            raw_md = fetch_fit_markdown(url)
            hash_part = hashlib.md5(url.encode()).hexdigest()[:8]
            unique_name = f"{url}_{hash_part}"

            if not raw_md.strip():
                print(f"[WARN] Empty markdown for {url}, skipping.")
                continue


            save_raw_data(unique_name, url, raw_md)
            print(f"[DEBUG] Saved raw_data for {url} as {unique_name}")

            unique_names.append(unique_name)
            url_name_map[unique_name] = url

        except Exception as e:
            print(f"[ERROR] Could not fetch raw markdown for {url}: {e}")

    # Step 2: Paginate and store each paginated article separately
    _, _, _, pagination_results = paginate_urls(
        unique_names=unique_names,
        model=selected_model,
        indication="",
        urls=list(url_name_map.values()),
        abm_context=abm_context
    )

    for result in pagination_results:
        page_urls = result.get("pagination_data", {}).get("page_urls", []) if hasattr(result, "pagination_data") else []

        for page_url in page_urls:
            try:
                md = fetch_fit_markdown(page_url)
                page_hash = hashlib.md5(page_url.encode()).hexdigest()[:8]
                page_unique_name = f"{page_url}_{page_hash}"

                save_raw_data(page_unique_name, url=page_url, raw_data=md)
                print(f"[DEBUG] Saved paginated data for {page_url} as {page_unique_name}")
                unique_names.append(page_unique_name)

            except Exception as e:
                print(f"[markdown] Error fetching page {page_url}: {e}")

    return unique_names
import time

def fetch_fit_markdown_with_retry(url, retries=2):
    for attempt in range(retries):
        try:
            return fetch_fit_markdown(url)
        except Exception as e:
            print(f"[Retry] Attempt {attempt+1} failed for {url}: {e}")
            time.sleep(1)
    return ""
