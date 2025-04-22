from api_management import get_supabase_client
supabase = get_supabase_client()

def read_raw_data(unique_name: str) -> str:
    try:
        response = supabase.table("scraped_data").select("raw_data").eq("unique_name", unique_name).execute()
        data = response.data
        return data[0].get("raw_data", "") if data else ""
    except Exception as e:
        print(f"[ERROR] read_raw_data failed for {unique_name}: {e}")
        return ""

def save_raw_data(unique_name: str, url: str, raw_data: str):
    try:
        supabase.table("scraped_data").upsert({
            "unique_name": unique_name,
            "url": url,
            "raw_data": raw_data,
        }).execute()
    except Exception as e:
        print(f"[ERROR] save_raw_data failed for {unique_name}: {e}")
