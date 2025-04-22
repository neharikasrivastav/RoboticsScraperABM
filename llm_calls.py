# llm_calls.py  – fully updated
import os, re, json, time, random
from typing import List, Dict, Any, Tuple

from litellm            import completion            # main call
from litellm.exceptions import RateLimitError
from assets             import MODELS_USED
from api_management     import get_api_key



# ════════════════════════════════════════════════════════════════════════
# helper‑utils (unchanged)
# ════════════════════════════════════════════════════════════════════════
def clean_article_url(url: str) -> str:
    return re.sub(r"[<>]", "", url.replace("</article", "")).strip()

def fix_url(url: str) -> str:
    if not isinstance(url, str):
        return url
    url = url.strip()
    m = re.search(r"(https?://[^\s<>]+)", url)
    if m:
        url = m.group(1)
    url = re.sub(r"</?article/+", "article/", url, flags=re.I)
    url = re.sub(r"[<>\"']", "", url)
    url = re.sub(r"/+>$", "", url).rstrip("/")
    if not url.startswith("http"):
        url = "https://" + url.lstrip("/")
    return url.replace("article/article/", "article/")

def clean_url_field(u: str) -> str:
    if not isinstance(u, str):
        return u
    m = re.findall(r"https?://[^\s<>\"]+", u)
    return (m[0] if m else u).strip()

def normalize_keys(obj):
    if isinstance(obj, dict):
        return {k.lower().replace(" ", "_"): normalize_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize_keys(i) for i in obj]
    return obj

# quick helper to clip very long strings at word‑boundary
def safe_truncate(txt: str, limit: int) -> str:
    if len(txt) <= limit:
        return txt
    cut = txt[:limit]
    return cut[: cut.rfind(" ")] + " …"

# ════════════════════════════════════════════════════════════════════════
# robust LLM wrapper
# ════════════════════════════════════════════════════════════════════════
MAX_ARTICLE_CHARS = 12_000       # ≈ 4–5 k tokens
MAX_ABM_CHARS     =  8_000
FALLBACK_MODEL    = "gpt-4.1-mini"

def call_llm_model(
    data: str,
    model: str,
    system_message: str,
    response_format=None,
    abm_context: str = "",
    MAX_RETRIES: int = 10,
    BASE_PAUSE:  int = 2,
    MAX_PAUSE:   int = 30,
) -> Tuple[Any, Dict[str, int], float]:
    """Send a prompt, parse JSON reply, retry on 429."""
    # choose model + set its key
    chosen = model or "gpt-4o"
    os.environ[list(MODELS_USED[chosen])[0]] = get_api_key(chosen) or ""

    # clip oversized inputs
    clipped_article = safe_truncate(data, MAX_ARTICLE_CHARS)
    clipped_abm     = safe_truncate(abm_context, MAX_ABM_CHARS) if abm_context else ""

    # build messages
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user",   "content": clipped_article}
    ]
    if clipped_abm:
        messages.insert(1, {"role": "system", "content": f"ABM Context:\n{clipped_abm}"})

    for attempt in range(MAX_RETRIES):
        try:
            resp = completion(model=chosen, messages=messages, seed=42)

            raw = resp.choices[0].message.content.strip("` \n")
            raw = raw[4:].strip() if raw.lower().startswith("json") else raw

            normal = normalize_keys(json.loads(raw))

            # post‑process listings
            needed = [
                "company", "company_info", "focus", "region", "company_size",
                "raised_funding", "recent_developments", "partnerships",
                "media_mentions", "humanoid_robotics_use_case",
                "single_use_cases", "task_streamlining", "project_launch_date",
                "relevancy_score", "correlation_reason", "article_name",
                "article_summary", "article_date", "article_url"
            ]
            if "listings" in normal:
                for lst in normal["listings"]:
                    lst.pop("source", None)
                    if lst.get("article_url"):
                        lst["article_url"] = clean_url_field(fix_url(lst["article_url"]))
                    for k in needed:
                        lst.setdefault(k, "")
                    lst.setdefault("article_summary", normal.get("article_summary", ""))

            final = response_format.model_validate(normal) if response_format else normal
            usage = resp.usage or {}
            return final, {
                "input_tokens":  usage.get("prompt_tokens",     0),
                "output_tokens": usage.get("completion_tokens", 0)
            }, 0.0

        except RateLimitError as err:
            wait = min(BASE_PAUSE * 2 ** attempt, MAX_PAUSE) + random.random()
            print(f"[429] sleeping {wait:.1f}s  ({attempt+1}/{MAX_RETRIES})")
            time.sleep(wait)
            if attempt == 2 and chosen != FALLBACK_MODEL:
                chosen = FALLBACK_MODEL
                print("↪︎ switching to fallback model:", chosen)
                os.environ[list(MODELS_USED[chosen])[0]] = get_api_key(chosen) or ""
            continue
        except Exception as err:
            bad = resp.choices[0].message.content if "resp" in locals() else "N/A"
            print("🛑 LLM / JSON error:", err)
            return {"raw_text": bad}, {"input_tokens": 0, "output_tokens": 0}, 0.0

    return (
        {"raw_text": "LLM call failed after repeated 429s."},
        {"input_tokens": 0, "output_tokens": 0},
        0.0
    )

# ════════════════════════════════════════════════════════════════════════
# small caching helpers
# ════════════════════════════════════════════════════════════════════════
scraped_cache: Dict[str, str] = {}

def summarize_article(article_url: str, article_text: str) -> str:
    if article_url in scraped_cache:
        return scraped_cache[article_url]

    msgs = [
        {"role": "system", "content": "Summarize this robotics article in 1–2 sentences."},
        {"role": "user",   "content": article_text}
    ]
    try:
        from openai import ChatCompletion
        summary = ChatCompletion.create(
            model="gpt-4o", messages=msgs, temperature=0.0, seed=42
        )["choices"][0]["message"]["content"]
    except Exception as e:
        print("[summarize_article] error:", e)
        summary = "Summary unavailable."

    scraped_cache[article_url] = summary
    return summary

# ════════════════════════════════════════════════════════════════════════
# simple parallel summariser (unchanged)
# ════════════════════════════════════════════════════════════════════════
def summarize_articles_parallel(
    markdowns: List[str],
    model: str,
    prompt: str,
    abm_context: str
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for md in markdowns:
        try:
            r = completion(
                model=model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user",   "content": md}
                ]
            )
            content = r.choices[0].message.content
            out.append(json.loads(content.strip("```json\n").strip("```")))
        except Exception as e:
            print("[summarize_articles_parallel] error:", e)
            out.append({"listings": [], "article_summary": "Failed"})
    return out
