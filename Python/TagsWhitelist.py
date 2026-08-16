"""
Gets all tags from steam store that are not hardware or software related.
"""

import requests
import json
import db

def get_tags_from_steam():
    url = "https://api.steampowered.com/IStoreService/GetTagList/v1/"
    input_json = {"language": "english"}
    params = {"key": "2CE4F8F8A27675F987B80830C91C3F47", "input_json": json.dumps(input_json)}
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()
    tags = data.get("response", {}).get("tags", {})

    return tags

def main():
    steam_tags = get_tags_from_steam()
    db_tags = db.fetch_all_tags()

    for tag in steam_tags:
        tag_name = tag["name"]
        if tag_name in db_tags:
            db_tags.pop(tag_name)
    
    print(db_tags.keys())



if __name__ == "__main__":
    main()