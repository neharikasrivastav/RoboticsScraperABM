import json
from typing import List, Dict
from assets import PROMPT_PAGINATION
from markdown_io import read_raw_data, save_raw_data
from api_management import get_supabase_client
from pydantic import BaseModel, create_model
from llm_calls import call_llm_model

supabase = get_supabase_client()

class PaginationModel(BaseModel):
    page_urls: List[str]

def get_pagination_response_format():
    return PaginationModel

def create_dynamic_listing_model(field_names: List[str]):
    return create_model('DynamicListingModel', **{f: (str, ...) for f in field_names})

def build_pagination_prompt(indications: str, url: str) -> str:
    prompt = PROMPT_PAGINATION + f"\nThe page being analyzed is: {url}\n"
    if indications.strip():
        prompt += f"These are the user's indications:\n{indications}\n\n"
    else:
        prompt += "No special user indications. Apply general pagination logic.\n\n"
    return prompt

def save_pagination_data(unique_name: str, pagination_data):
    if hasattr(pagination_data, "dict"):
        pagination_data = pagination_data.dict()
    if isinstance(pagination_data, str):
        try:
            pagination_data = json.loads(pagination_data)
        except json.JSONDecodeError:
            pagination_data = {"raw_text": pagination_data}

    # Preserve existing raw_data while updating pagination
    raw_data = read_raw_data(unique_name)
    save_raw_data(unique_name, url="", raw_data=raw_data)  # optional, depending on your schema

    supabase.table("scraped_data").update({
        "pagination_data": pagination_data
    }).eq("unique_name", unique_name).execute()

    print(f"\033[35mINFO: Pagination data saved for {unique_name}\033[0m")

def paginate_urls(unique_names: List[str], model: str, user_hint: str, urls: List[str], abm_context: str = ""):
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0
    pagination_results = []

    for uniq, current_url in zip(unique_names, urls):
        raw_data = read_raw_data(uniq)
        if not raw_data:
            print(f"[WARN] No raw_data found for {uniq}, skipping pagination.")
            continue

        prompt = build_pagination_prompt(user_hint, current_url)
        schema = get_pagination_response_format()

        pag_data, token_counts, cost = call_llm_model(
            data=raw_data,
            response_format=schema,
            model=model,
            system_message=prompt,
            abm_context=abm_context
        )

        save_pagination_data(uniq, pag_data)

        total_input_tokens += token_counts["input_tokens"]
        total_output_tokens += token_counts["output_tokens"]
        total_cost += cost

        pagination_results.append({
            "unique_name": uniq,
            "url": current_url,
            "pagination_data": pag_data
        })

    return total_input_tokens, total_output_tokens, total_cost, pagination_results
