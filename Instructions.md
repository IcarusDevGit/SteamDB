TagsScraper.py needs to use https://steamspy.com/api.php?request=appdetails&appid={appid} to fetch tags, not the Steam API.
The script will receive a list of games from the FetchTop100Weekly.py script. This list will have the appid of each game.
Using this appid, the script should consult the db for each game by appid and if the game is not on the database then it should
send the appid, name and tags to db.py to be upserted. 
SteamSpy returns the following for each game: (using counter-strike as an example)
{
  "appid": 10,
  "name": "Counter-Strike",
  "developer": "Valve",
  "publisher": "Valve",
  "score_rank": "",
  "positive": 243818,
  "negative": 6427,
  "userscore": 0,
  "owners": "10,000,000 .. 20,000,000",
  "average_forever": 0,
  "average_2weeks": 0,
  "median_forever": 0,
  "median_2weeks": 0,
  "price": "999",
  "initialprice": "999",
  "discount": "0",
  "ccu": 7323,
  "languages": "English, French, German, Italian, Spanish - Spain, Simplified Chinese, Traditional Chinese, Korean",
  "genre": "Action",
  "tags": {
    "Action": 5504,
    "FPS": 4929,
    "Multiplayer": 3474,
    "Shooter": 3419,
    "Classic": 2849,
    "Team-Based": 1921,
    "First-Person": 1761,
    "Competitive": 1654,
    "Tactical": 1391,
    "1990's": 1246,
    "e-sports": 1232,
    "PvP": 928,
    "Old School": 829,
    "Military": 665,
    "Strategy": 642,
    "Survival": 323,
    "Score Attack": 304,
    "1980s": 285,
    "Assassin": 248,
    "Nostalgia": 206
  }
}

The numbers from the "tags" dictionary are votes, not the id of the tags, and are useless to me, ignore them. Only retrieve the tag and genres (some games have more than one genre.) names. They both should be condensed to one tags list.
There's already a tags table on my database, the ids can be fetched by querying the table with the tag names.

I also need a method to update the tags of any game that may be missing tags from the games table on the database. 
This can be achieved by querying the database for all games that have empty tags (tags = {}), and then using the method 
above to fetch the tags for each game and upsert them to the database.

All changes should be made only in AppendTags.py and TagsScraper.py if necessary. If any other changes are necessary ask for permission
before making changes.

If any additional context or informations is needed ask me for it before starting to code.