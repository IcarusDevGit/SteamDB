I need the price and discount of a game in a given date for my data analysis
This information can be acquired through https://api.isthereanydeal.com/
The script responsible for this will be PriceScraper.py
main.py will call this script to fetch price and discount of games from the top 100 list for a specific date
PriceScraper.py will return the price and discount of each game
The result of main.py should now also include two more columns (price and discount) for each game

The result should be the following csv: (Writen by WriteCSV.py)
rank,appid,name,tags,rating,price,discount

All the methods required for getting the price and discount information should be in PriceScraper.py
UpdateDB.py also needs a function to update the weeksheet table with the new price and discount information for entries where these values are null (the function should be used through terminal like all other methods in UpdateDB.py)

If any additional context or information is needed ask me for it before starting to code.