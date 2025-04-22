

import logging
import json
import re
from typing import List, Optional
from urllib.parse import urljoin
from llm_calls import MAX_ARTICLE_CHARS as MAX_CHARS

from pydantic import BaseModel, create_model, Field
from bs4 import BeautifulSoup

from llm_calls import summarize_articles_parallel
from assets import ROBOTICS_SYSTEM_MESSAGE
from markdown_io import read_raw_data
from api_management import get_supabase_client
from utils import enrich_company_metadata, correlate_with_abm, extract_launch_date_from_article
from abm_docs import get_abm_report_text

# ─── Setup ─────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
supabase = get_supabase_client()

# ─── Dynamic Pydantic Models ───────────────────────────────────────────────────

def create_dynamic_listing_model(field_names: List[str]):
    required_fields = [
        "Company", "Company Info", "Focus", "Region",
        "Humanoid Robotics Use Case", "Single Use Cases", "Task Streamlining",
        "Raised Funding", "Recent Developments", "Partnerships",
        "Relevancy Score", "Correlation Reason",
        "Article Name", "Article Summary", "Article Date", "Article URL",
        "Project Launch Date"
    ]
    all_fields = list(set(required_fields + field_names))
    defs = {
        field: (Optional[str], Field(default=None, alias=field.lower().replace(" ", "_")))
        for field in all_fields
    }
    class Config:
        populate_by_name = True
        extra = "allow"
    return create_model("DynamicListingModel", __config__=Config, **defs)

def create_listings_container_model(listing_model: BaseModel):
    class Config:
        populate_by_name = True
        extra = "allow"
    return create_model(
        "DynamicListingsContainer",
        __config__=Config,
        listings=(List[listing_model], Field(..., alias="listings"))
    )

# ─── Helpers ───────────────────────────────────────────────────────────────────

def sanitize_article_url(raw_url: str) -> str:
    if not raw_url or not isinstance(raw_url, str):
        return "TBD"
    m = re.search(r'<(https?://[^>\s]+)>', raw_url)
    if m:
        return m.group(1)
    cleaned = raw_url.strip().split("<")[0].split(">")[-1].strip()
    return cleaned if cleaned.startswith(("http://", "https://")) else "TBD"

def save_formatted_data(unique_name: str, formatted_data):
    if isinstance(formatted_data, str):
        try:
            data = json.loads(formatted_data)
        except json.JSONDecodeError:
            data = {"raw_text": formatted_data}
    elif hasattr(formatted_data, "dict"):
        data = formatted_data.dict()
    else:
        data = formatted_data
    supabase.table("scraped_data").update({"formatted_data": data}).eq("unique_name", unique_name).execute()
    logging.info(f"Saved formatted_data for {unique_name}")

# ─── Main Scraping & Extraction ────────────────────────────────────────────────

def scrape_urls(unique_names: List[str], fields: List[str], selected_model: str, abm_context: str = ""):
    """
    For each raw article (in Supabase under unique_name) run LLM extraction:
    1) Summarize + extract into JSON listings
    2) Enrich each listing (metadata, ABM correlation, launch date)
    3) Persist formatted_data back to Supabase
    Returns token usage & a list of parsed_results.
    """
    total_in, total_out, total_cost = 0, 0, 0
    parsed_results = []

    # Build Pydantic schema
    DynamicListingModel = create_dynamic_listing_model(fields)
    DynamicContainer   = create_listings_container_model(DynamicListingModel)

    if not abm_context:
        abm_context = get_abm_report_text()

    # Read all markdowns
    markdowns, valid_uniques = [], []
    for uniq in unique_names:
        md = read_raw_data(uniq)
        if md:
            md = md[:MAX_CHARS]  # truncate here
            markdowns.append(md)
            valid_uniques.append(uniq)
        else:
            logging.warning(f"No raw_data for {uniq}, skipping.")

    

    # 1) Summarize & JSON‑extract listings in parallel
    logging.info(f"Extracting {len(markdowns)} articles with model {selected_model}")
    results = summarize_articles_parallel(markdowns, selected_model, ROBOTICS_SYSTEM_MESSAGE, abm_context)

    # 2) Post‑process each listing
    for uniq, parsed in zip(valid_uniques, results):
        try:
            listings = parsed.get("listings", [])
            for lst in listings:
                # a) Enrich company metadata & ABM correlation
                enrich_company_metadata(lst, selected_model)
                correlate_with_abm(lst, abm_context, selected_model)
                # b) Extract launch date if needed
                if lst.get("Project Launch Date", "TBD") == "TBD":
                    ld = extract_launch_date_from_article(read_raw_data(uniq), selected_model)
                    lst["Project Launch Date"] = ld.get("project_launch_date", "TBD")
                # c) Clean up URL
                lst["Article URL"] = sanitize_article_url(lst.get("Article URL", ""))

            # 3) Save back to Supabase
            save_formatted_data(uniq, parsed)

            parsed_results.append({
                "unique_name": uniq,
                "parsed_data": parsed,
                "status": "success"
            })

        except Exception as e:
            logging.error(f"Processing failure for {uniq}: {e}")
            parsed_results.append({
                "unique_name": uniq,
                "parsed_data": {},
                "status": "failed",
                "error": str(e)
            })

    return total_in, total_out, total_cost, parsed_results
