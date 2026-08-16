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

if __name__ == "__main__":
    # Test the function with a known game, e.g., Cyberpunk 2077 (1091500)
    test_appid = 1091500
    print(f"Fetching tags for AppID {test_appid}...")
    tags = fetch_tags(test_appid)
    print(f"Found {len(tags)} tags:")
    print(tags)
