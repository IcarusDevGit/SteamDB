AppendTags.py and TagsScraper.py needs to be reworked:
TagsScraper.py should be divided into two parts:
    1. FetchSteamAPITags.py - Fetches tags from the Steam API and returns a list of tags.
    2. FetchSteamStoreTags.py - Fetches tags from steam store (E.g. https://store.steampowered.com/app/10/CounterStrike/ for AppId=10) *Done

The steam store page has all the information provided by SteamSpy, meaning it's no longer necessary.

AppendTags.py will call both of those methods after being given a dictionary with the appid and game name
After getting the tags from all three sources it needs to send the data to WriteCSV.py
WriteCSV.py will write a .csv with all entries containing game name, appid and the tags ids, this .csv is necessary for data validation before commiting data to the database.

Requirements:
    1. No game should have duplicated tagids in the tags collumn
    2. Any tags ids not found in the database are be written to a separate collumn unresolved_tags in the .csv, additionally I need a .txt or .md file with a list containing all unresolved tags. I will then go through these tags and decide if any of them should be added to TagsExceptions.JSON. After validation, I need a method to add all unresolved tags not on TagsExceptions.JSON to the database with a generated unique id with 6 digits.
    

