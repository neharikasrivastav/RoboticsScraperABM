
import os
import json
import uuid
import requests
from datetime import datetime, timedelta
from litellm import completion
from assets import MODELS_USED
from api_management import get_api_key
from news_utils import get_media_mentions

def generate_unique_name(prefix="doc"):
    """
    Generate a unique name for the document using a prefix and a UUID.
    """
    return f"{prefix}_{uuid.uuid4().hex[:8]}"

def generate_pdf_summary(pdf_text: str, model: str):
    """
    Generate a detailed summary of the ABM PDF content.
    The summary will cover financial performance, strategic goals, partnerships, etc.
    """
    # Set API key for the chosen model
    if model not in MODELS_USED:
        print(f"[❌ Error] Unknown model '{model}' not found in MODELS_USED. Skipping.")
        return
    env_var = list(MODELS_USED[model])[0]
    api_key = get_api_key(model)
    if api_key:
        os.environ[env_var] = api_key

    prompt = f"""
You are an assistant that generates detailed summaries of stakeholder documents. Please read the following ABM PDF content and provide a detailed summary.

The summary should include:
- Key highlights
- Important sections such as strategic updates, financial performance, or innovation updates
- Relevant actions or strategic plans
- Any mentions of future directions, key business priorities, or goals
- If there are tables, charts, or other data-heavy sections, summarize their key points

Your summary should cover the following aspects:
- Financial performance and key metrics
- Innovation updates or strategic goals
- Any changes or developments in ABM's business areas (maintenance, sustainability, facility management, etc.)
- Key partnerships or business collaborations mentioned
- Any other significant details that ABM stakeholders would need to focus on

---
{pdf_text}

Only return a clear and concise summary, without additional commentary, formatting, or unnecessary details.
"""

    response = completion(
        model=model,
        messages=[
            {"role": "system", "content": "You summarize stakeholder PDFs in detail, including financial performance, strategic goals, and other significant details."},
            {"role": "user", "content": prompt}
        ],
        seed=42
    )
    try:
        return response.choices[0].message.content.strip()
    except Exception:
        return "Summary unavailable."

def enrich_company_metadata(listing, model: str = "gpt-4o"):
    """
    Extract and enrich company metadata using the company's own sources (website + article).
    Fills in fields like Company Info, Region, Focus, Company Size, Raised Funding, etc.
    """
    website_text = listing.get("company_website_content", "")
    article_text = listing.get("article_text", "")
    listing.setdefault("article_summary", listing.get("Article Summary", "N/A"))

    if not (website_text or article_text):
        print("[enrich_company_metadata] No website or article content available.")
        return

    combined_source = f"WEBSITE:\n{website_text}\n\nARTICLE:\n{article_text}"

    # Set API key
    if model not in MODELS_USED:
        print(f"[❌ Error] Unknown model '{model}' not found in MODELS_USED. Skipping.")
        return
    env_var = list(MODELS_USED[model])[0]
    api_key = get_api_key(model)
    if api_key:
        os.environ[env_var] = api_key

    prompt = f"""
You are a Robotics Company Profiling AI. Your task is to extract structured metadata from the following company sources:

- WEBSITE content (for mission, use case, product details)
- ARTICLE content (for external context like product launch, funding, and industry news)

Your job is to combine these two sources into one detailed company profile in JSON format.

--- COMPANY SOURCE CONTENT START ---
{combined_source}
--- COMPANY SOURCE CONTENT END ---

Use the structure below and fill in each field with detailed, informative responses. Be concise but insightful.

{{
  "company_info": "Summarize what the company builds with clear mention of its robotics applications...",
  "region": "Country or region where the company is based.",
  "focus": "2–5 word robotics focus.",
  "company_size": "Small / Medium / Large.",
  "capital_raised": "Total capital raised, or 'Not Disclosed'.",
  "funding_stage_inferred": "Seed / Series A / ... / Unknown.",
  "recent_developments": "List 2–3 key updates from the past 6–12 months.",
  "partnerships": "Significant partnerships or 'None'.",
  "humanoids_focus": "Yes/No — explanation of any humanoid work.",
  "single_use_case_type": "Yes/No — rationale on single-use focus.",
  "streamlined_tasks": "Tasks optimized by their robots.",
  "project_launch_date": "Month Year or 'TBD'."
}}

Output only a valid JSON object. No explanations, markdown, or extra formatting.
"""

    try:
        resp = completion(
            model=model,
            messages=[
                {"role": "system", "content": "You extract company profile insights from website and article text."},
                {"role": "user", "content": prompt}
            ],
            seed=42
        )
        enriched = json.loads(resp.choices[0].message.content)
    except Exception as e:
        print("[enrich_company_metadata] JSON parse error:", e)
        return

    # Fallback defaults
    enriched.setdefault("region", "Unknown")
    enriched.setdefault("focus", "Not Available")
    enriched.setdefault("company_size", "Unknown")
    enriched.setdefault("capital_raised", "Not Disclosed")
    enriched.setdefault("recent_developments", "No updates available")
    enriched.setdefault("partnerships", "None")
    enriched.setdefault("humanoids_focus", "No")
    enriched.setdefault("single_use_case_type", "No")
    enriched.setdefault("streamlined_tasks", "")
    enriched.setdefault("project_launch_date", "TBD")
    enriched.setdefault("company_info", "Not provided")

    # Map extracted keys into your Pydantic field names
    mapping = {
        "company_info":         "Company Info",
        "focus":                "Focus",
        "region":               "Region",
        "company_size":         "Company Size",
        "capital_raised":       "Raised Funding",
        "recent_developments":  "Recent Developments",
        "partnerships":         "Partnerships",
        "humanoids_focus":      "Humanoid Robotics Use Case",
        "single_use_case_type": "Single Use Cases",
        "streamlined_tasks":    "Task Streamlining",
        "project_launch_date":  "Project Launch Date",
    }
    for src, dst in mapping.items():
        if src in enriched:
            listing[dst] = enriched[src]

    # Store a description field for downstream prompts
    listing["description"] = enriched.get("company_info", "Not provided")

    # Fetch media mentions count
    try:
        count = get_media_mentions(listing.get("Company", ""))
        listing["Media Mentions"] = count
    except Exception as e:
        print("[enrich_company_metadata] media mentions error:", e)

def build_prompt(fields, content):
    """
    Utility to build a generic extraction prompt.
    """
    return (
        "You are an information extraction assistant.\n"
        f"Fields to extract: {', '.join(fields)}\n\n"
        f"Content:\n{content}"
    )

def correlate_with_abm(listing, abm_context: str, model: str = "gpt-4o"):
    """
    Evaluate how well a company aligns with ABM Industries’ strategic goals.
    Updates listing with "Correlation Reason" (A–D) and "Relevancy Score" (1–5).
    """
    # Set API key
    if model not in MODELS_USED:
        print(f"[❌ Error] Unknown model '{model}' not found in MODELS_USED. Skipping.")
        return
    env_var = list(MODELS_USED[model])[0]
    api_key = get_api_key(model)
    if api_key:
        os.environ[env_var] = api_key

    # Gather company data for the prompt
    company_data = {
        "description":           listing.get("description", ""),
        "focus":                 listing.get("Focus", ""),
        "region":                listing.get("Region", ""),
        "capital_raised":        listing.get("Raised Funding", ""),
        "recent_developments":   listing.get("Recent Developments", ""),
        "partnerships":          listing.get("Partnerships", ""),
        "streamlined_tasks":     listing.get("Task Streamlining", ""),
        "humanoids_focus":       listing.get("Humanoid Robotics Use Case", ""),
        "single_use_case_type":  listing.get("Single Use Cases", ""),
        "project_launch_date":   listing.get("Project Launch Date", ""),
        "company_size":          listing.get("Company Size", "")
    }

    prompt = f"""
You are an expert analyst evaluating how well a robotics company aligns with ABM Industries' strategic goals.

ABM Context:
\"\"\"{abm_context[:8000]}\"\"\"

Company Details:
{json.dumps(company_data, indent=2)}

TASK:
A. Historical ABM Business Activity — overlap with services?
B. ABM’s Future Strategic Plans — innovation alignment?
C. Company’s Innovation or Value Proposition?
D. Stage of Technology — maturity assessment?

For each letter, write 1–2 clear sentences. Only return plain text lines prefixed A.–D.
"""

    try:
        # Step 1: get A–D reasoning
        resp = completion(
            model=model,
            messages=[
                {"role": "system", "content": "You are a strategic evaluator."},
                {"role": "user", "content": prompt}
            ],
            seed=42
        )
        reasoning = resp.choices[0].message.content.strip()
        listing["Correlation Reason"] = reasoning

        # Step 2: derive a numeric score
        score_resp = completion(
            model=model,
            messages=[
                {"role": "system", "content": "You assign a fit score from 1 to 5."},
                {"role": "user", "content": f"Based on the following A–D reasoning, give me a number 1–5:\n\"\"\"{reasoning}\"\"\""}
            ],
            seed=42
        )
        score = score_resp.choices[0].message.content.strip()
        listing["Relevancy Score"] = score if score in {"1","2","3","4","5"} else "1"

    except Exception as e:
        print("[correlate_with_abm] Error:", e)
        listing.setdefault("Correlation Reason", "No reasoning available.")
        listing.setdefault("Relevancy Score", "1")

def extract_single_use_case(listing, model: str = "gpt-4o"):
    """
    Identify if the company develops single‑use robots.
    """
    website = listing.get("company_website_content", "")
    if not website:
        return

    env_var = list(MODELS_USED[model])[0]
    api_key = get_api_key(model)
    if api_key:
        os.environ[env_var] = api_key

    prompt = """
You are an AI assistant. Identify if the company’s robots are single‑use case.
Return JSON: {"single_use_case_type":"Yes/No","description":"..."}
"""
    resp = completion(
        model=model,
        messages=[{"role":"system","content":"You extract single-use robotics info."},
                  {"role":"user","content":prompt}],
        seed=42
    )
    try:
        obj = json.loads(resp.choices[0].message.content)
        listing.update(obj)
    except Exception as e:
        print("[extract_single_use_case] JSON parse error:", e)

def extract_task_streamlining(listing, model: str = "gpt-4o"):
    """
    Identify which tasks the company streamlines via robotics.
    """
    website = listing.get("company_website_content", "")
    if not website:
        return
    
    if model not in MODELS_USED:
        print(f"[❌ Error] Unknown model '{model}' not found in MODELS_USED. Skipping.")
        return

    env_var = list(MODELS_USED[model])[0]
    api_key = get_api_key(model)
    if api_key:
        os.environ[env_var] = api_key

    prompt = """
You are an AI assistant. Determine if the company uses robotics to streamline tasks.
Return JSON: {"task_streamlining":"Yes/No","description":"..."}
"""
    resp = completion(
        model=model,
        messages=[{"role":"system","content":"You extract task streamlining info."},
                  {"role":"user","content":prompt}],
        seed=42
    )
    try:
        obj = json.loads(resp.choices[0].message.content)
        listing.update(obj)
    except Exception as e:
        print("[extract_task_streamlining] JSON parse error:", e)

def extract_humanoid_use_case(listing, model: str = "gpt-4o"):
    """
    Identify if the company develops humanoid robots.
    """
    website = listing.get("company_website_content", "")
    if not website:
        return

    env_var = list(MODELS_USED[model])[0]
    api_key = get_api_key(model)
    if api_key:
        os.environ[env_var] = api_key

    prompt = """
You are an AI assistant. Check if the company works on humanoid robots.
Return JSON: {"humanoid_use_case":"Yes/No","description":"..."}
"""
    resp = completion(
        model=model,
        messages=[{"role":"system","content":"You extract humanoid robotics info."},
                  {"role":"user","content":prompt}],
        seed=42
    )
    try:
        obj = json.loads(resp.choices[0].message.content)
        listing.update(obj)
    except Exception as e:
        print("[extract_humanoid_use_case] JSON parse error:", e)

def extract_partnerships(listing, model: str = "gpt-4o"):
    """
    Extract recent or strategic partnerships.
    """
    website = listing.get("company_website_content", "")
    if not website:
        return

    env_var = list(MODELS_USED[model])[0]
    api_key = get_api_key(model)
    if api_key:
        os.environ[env_var] = api_key

    prompt = """
You are an AI assistant. Extract any partnerships the company has.
Return JSON: {"partnerships":"...","description":"..."}
"""
    resp = completion(
        model=model,
        messages=[{"role":"system","content":"You extract partnerships from web content."},
                  {"role":"user","content":prompt}],
        seed=42
    )
    try:
        obj = json.loads(resp.choices[0].message.content)
        listing.update(obj)
    except Exception as e:
        print("[extract_partnerships] JSON parse error:", e)

def extract_launch_date_from_article(article_text: str, model: str = "gpt-4o"):
    """
    Extract the launch date of any robotics project mentioned explicitly.
    Returns {"project_launch_date":"Month Year" or "TBD"}.
    """
    env_var = list(MODELS_USED[model])[0]
    api_key = get_api_key(model)
    if api_key:
        os.environ[env_var] = api_key

    prompt = f"""
You are a date extraction assistant. Find the launch date of any robotics project only if clearly stated.
Article:
\"\"\"{article_text[:4000]}\"\"\"
Return JSON: {{ "project_launch_date": "Month Year" or "TBD" }}
"""
    resp = completion(
        model=model,
        messages=[{"role":"system","content":"You extract project launch dates from tech news."},
                  {"role":"user","content":prompt}],
        seed=42
    )
    try:
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print("[extract_launch_date_from_article] JSON parse error:", e)
        return {"project_launch_date": "TBD"}
