import os
import requests
from api_management import get_api_key

def get_media_mentions(company_name: str) -> int:
    """Returns number of media mentions in the last 30 days using GNews API"""
    api_key = get_api_key("gnews")
    if not api_key:
        return 0

    query = f'"{company_name}"'
    url = f"https://gnews.io/api/v4/search?q={query}&lang=en&max=100&from=30d&token={api_key}"

    try:
        response = requests.get(url)
        data = response.json()
        return min(len(data.get("articles", [])), 100)  # GNews free plan caps at 100
    except Exception as e:
        print(f"[get_media_mentions] Error fetching data: {e}")
        return 0
