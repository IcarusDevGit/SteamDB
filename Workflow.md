Read this entire file before starting to develop the code 

Call main.py
Fetch top 100 data (appid, name, price, rank) and return data
Get games from data and append tags with AppendTags.py to any games not found on db
Append ratings to data with AppendRatings.py
Write data to .csv using WriteCSV.py
Upsert entries from .csv to weeksheet table on db using script on db.py. Create method for this but comment it out, I only want to upsert anything to db after the code is verified by me

data structure returned from FetchTop100Weekly.py:
[{'rank': 1, 'appid': 730, 'name': 'Counter-Strike 2', 'price': 0}], 
final data structure to write to .csv and then to db should be:
[{'rank': 1, 'appid': 730, 'price': 0, 'rating': 0.95}], 

changes should only be made to main.py, AppendRatings.py and  WriteCSV.py
If necessary to alter any other files ask for permission
Files to consider: all the ones that should be modified + AppendTags.py, TagsScraper.py, RatingScraper.py, FetchTop100Weekly.py
Ignore any other files

If any other information is required ask for clarification before starting to develop the code