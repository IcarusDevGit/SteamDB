import requests
from bs4 import BeautifulSoup

def fetch_tags(appid):
    """
    Fetches user-defined tags for a given appid directly from the Steam store HTML page.
    Bypasses the age gate by providing appropriate cookies.
    
    Args:
        appid (int or str): The Steam application ID.
        
    Returns:
        list of str: A list of tags extracted from the store page.
    """
    url = f"https://store.steampowered.com/app/{appid}/"
    
    # Cookies to bypass age verification on mature games
    cookies = {
        'birthtime': '283993201',
        'lastagecheckage': '1-January-1979',
        'wants_mature_content': '1'
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(url, cookies=cookies, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # User tags on the Steam store page are typically in anchor elements with the class 'app_tag'
        tag_elements = soup.find_all('a', class_='app_tag')
        
        tags = []
        for tag_elem in tag_elements:
            tag_name = tag_elem.get_text(strip=True)
            # Sometimes there is a "+" sign as the last tag element to add new tags, skip it
            if tag_name and tag_name != "+":
                if tag_name not in tags:
                    tags.append(tag_name)
                    
        return tags
        
    except requests.RequestException as e:
        print(f"[FetchSteamStoreTags] Network error fetching tags for appid {appid}: {e}")
        return []
    except Exception as e:
        print(f"[FetchSteamStoreTags] Unexpected error fetching tags for appid {appid}: {e}")
        return []


CONTENT_DESCRIPTORS_MAP = {
    1: "Some Nudity or Sexual Content",
    2: "Frequent Violence or Gore",
    3: "Adult Only Sexual Content",
    4: "Frequent Nudity or Sexual Content",
    5: "General Mature Content",
}


def fetch_store_categories(appid):
    """
    Fetches categories and content descriptors for a given appid from Steam Store API.
    Returns:
        dict: {int_id: str_name} mapping category/descriptor IDs to their descriptions.
    """
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&cc=us&l=english"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        app_data = data.get(str(appid), {})
        if not app_data.get("success"):
            return {}

        inner_data = app_data.get("data", {})
        categories = inner_data.get("categories", [])

        cat_map = {}
        for c in categories:
            cid = c.get("id")
            desc = c.get("description", "").strip()
            if cid is not None and desc:
                cat_map[int(cid)] = desc

        # Content descriptors
        cd_ids = inner_data.get("content_descriptors", {}).get("ids", [])
        for cid in cd_ids:
            if isinstance(cid, int) and cid in CONTENT_DESCRIPTORS_MAP and cid not in cat_map:
                cat_map[cid] = CONTENT_DESCRIPTORS_MAP[cid]

        return cat_map
    except Exception as e:
        print(f"[FetchSteamStoreTags] Error fetching categories for appid {appid}: {e}")
        return {}


def fetch_category_name(appid, category_id):
    """
    Fetch a single category name for a given appid and category ID.
    Returns description string if found, or None.
    """
    if category_id in CONTENT_DESCRIPTORS_MAP:
        return CONTENT_DESCRIPTORS_MAP[category_id]

    cat_map = fetch_store_categories(appid)
    return cat_map.get(int(category_id))


if __name__ == "__main__":
    # Test the function with a known game, e.g., Cyberpunk 2077 (1091500)
    test_appid = 1091500
    print(f"Fetching tags for AppID {test_appid}...")
    tags = fetch_tags(test_appid)
    print(f"Found {len(tags)} tags:")
    print(tags)

    print(f"\nFetching categories for AppID {test_appid}...")
    cats = fetch_store_categories(test_appid)
    print(f"Found {len(cats)} categories:")
    print(cats)

