
import os
import streamlit as st
import pandas as pd
import numpy as np
import json
import re
import sys
import asyncio
from urllib.parse import urlparse

from crawl import crawl_and_extract
from scraper import scrape_urls
from assets import MODELS_USED
from api_management import get_supabase_client
from abm_docs import extract_text_from_pdf, get_abm_report_text
from utils import generate_pdf_summary
from scraping_strategies import SCRAPING_STRATEGIES



def get_strategy(url: str) -> str:
    domain = urlparse(url).netloc.replace("www.", "")
    return SCRAPING_STRATEGIES.get(domain, "static")


# On Windows, use the ProactorEventLoop
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Streamlit page setup
st.set_page_config(page_title="🤖 Robotics Articles Scraper", layout="wide")
supabase = get_supabase_client()
if not supabase:
    st.error("🚨 Supabase is not configured! Please set SUPABASE_URL and SUPABASE_ANON_KEY in the sidebar.")
    st.stop()

st.title("🤖 Robotics Articles Scraper")

#
# Sidebar: API Keys + ABM PDF
#
st.sidebar.header("🔑 API & ABM Settings")

# API keys for each model
for model, keys in MODELS_USED.items():
    for key in keys:
        value = st.session_state.get(f"{key}_{model}", "")
        if value:
            os.environ[key] = value

# Supabase
st.sidebar.text_input("SUPABASE URL", key="SUPABASE_URL")
st.sidebar.text_input("SUPABASE ANON KEY", type="password", key="SUPABASE_ANON_KEY")

# ABM PDF and summary toggle
generate_summary = st.sidebar.checkbox("Generate summary from uploaded ABM PDF")
abm_file = st.sidebar.file_uploader("Upload ABM PDF", type=["pdf"])
abm_context = ""
abm_summary = ""
if abm_file:
    import fitz
    from litellm.exceptions import RateLimitError
    doc = fitz.open(stream=abm_file.read(), filetype="pdf")
    abm_context = "\n\n".join([page.get_text() for page in doc])
    if generate_summary:
        try:
            abm_summary = generate_pdf_summary(abm_context, "gpt-4o")
        except RateLimitError:
            st.sidebar.warning("Rate limit on gpt-4o, falling back to gpt-4o-mini")
            abm_summary = generate_pdf_summary(abm_context, "gpt-4o-mini")

#
# URL input controls
#
st.sidebar.header("➕ Add Article URLs")
if "urls" not in st.session_state:
    st.session_state.urls = []

url_text = st.sidebar.text_area("Enter URLs (comma/newline separated)")
auto_paginate = st.sidebar.checkbox("Auto‑follow pagination", value=True)
use_scroll    = st.sidebar.checkbox("Use scroll‑based pagination", value=False)
num_pages     = st.sidebar.number_input("Pages to crawl", min_value=1, max_value=20, value=3)

if st.sidebar.button("Add URLs"):
    for u in re.split(r"[,\n\s]+", url_text.strip()):
        if u and u not in st.session_state.urls:
            st.session_state.urls.append(u)
    st.rerun()

if st.session_state.urls:
    for u in st.session_state.urls:
        st.sidebar.write(f"- {u}")

#
# Start scraping
#
model_choice = st.sidebar.selectbox("Select LLM model", list(MODELS_USED.keys()))

if st.sidebar.button("🚀 Start Scraping"):
    if not st.session_state.urls:
        st.sidebar.error("Please add at least one URL.")
    else:
        all_unique_names = []
        for url in st.session_state.urls:
            strategy = get_strategy(url)
            use_scroll_this = strategy in ["scroll", "load_more"]
            use_browser_this = strategy == "load_more"

            print(f"[DEBUG] Crawling {url} | Strategy: {strategy} | Scroll: {use_scroll_this} | Browser: {use_browser_this}")

            unique_names = crawl_and_extract(
                base_urls=[url],
                model=model_choice,
                user_hint="",
                abm_context=abm_context,
                max_pages=num_pages,
                use_scroll=use_scroll_this,
                use_browser_fetch=use_browser_this,
            )

            all_unique_names.extend(unique_names)

        
        del st.session_state.urls

        st.session_state["model_selection"] = model_choice
        st.session_state["unique_names"]     = all_unique_names
        st.session_state["scraping_state"]   = "scraping"

        # Now your existing `if st.session_state["scraping_state"] == "scraping":` block will fire

        st.rerun()

#
# Processing & display
#
if st.session_state.get("scraping_state") == "scraping":

    with st.spinner("🛠️ Processing articles…"):
        in_t, out_t, cost_t, parsed = scrape_urls(
            st.session_state.unique_names,
            # These are your 18 default fields
            [
                "Article Name", "Article Summary", "Article Date", "Article URL",
                "Company", "Company Info", "Region", "Company Size", "Raised Funding",
                "Recent Developments", "Partnerships", "Media Mentions", "Focus",
                "Humanoid Robotics Use Case", "Single Use Cases", "Task Streamlining",
                "Project launch date", "Relevancy Score", "Correlation Reason"
            ],
            model_choice,
            abm_context
        )
    st.success("✅ Done scraping & parsing!")

    # Show ABM summary if any
    if abm_summary:
        st.subheader("📄 ABM PDF Summary")
        st.write(abm_summary)

    # Flatten results into a DataFrame
    records = []
    for item in parsed:
        data = item.get("parsed_data", {})
        if hasattr(data, "model_dump"):
            data = data.model_dump()
        ls = data.get("Listings") or data.get("listings") or []
        for listing in ls:
            # carry over article_summary if needed
            listing["Article Summary"] = data.get("article_summary", listing.get("Article Summary", ""))
            records.append(listing)

    if not records:
        st.warning("No listings found in the parsed output.")
        st.json(parsed)
        st.stop()

    df = pd.DataFrame(records)
    # Normalize column names
    df.columns = [str(c).strip().title() for c in df.columns]
    df.replace("", np.nan, inplace=True)

    # Optional: filter by relevancy
    if "Relevancy Score" in df.columns:
        df["Relevancy Score"] = pd.to_numeric(df["Relevancy Score"], errors="coerce")
        min_score = st.slider("🎯 Min Relevancy Score", 1, 5, 3)
        df = df[df["Relevancy Score"] >= min_score]

    # Display paginated table
    BATCH_SIZE = 5
    total = len(df)
    pages = (total + BATCH_SIZE - 1) // BATCH_SIZE
    if "page" not in st.session_state:
        st.session_state.page = 0

    start = st.session_state.page * BATCH_SIZE
    end   = start + BATCH_SIZE
    st.dataframe(df.iloc[start:end], use_container_width=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("⬅️ Prev") and st.session_state.page > 0:
            st.session_state.page -= 1
            st.rerun()
    with col2:
        st.markdown(f"Page **{st.session_state.page+1}/{pages}**")
    with col3:
        if st.button("Next ➡️") and end < total:
            st.session_state.page += 1
            st.rerun()

    # Download buttons
    st.subheader("💾 Download Data")
    json_data = json.dumps(records, indent=2)
    st.download_button("Download JSON", data=json_data, file_name="scraped_data.json")

    if not df.empty:
        csv_data = df.to_csv(index=False)
        st.download_button("Download CSV", data=csv_data, file_name="scraped_data.csv")
