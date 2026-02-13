"""
Test provider - look at all events for best data
"""
import sys
sys.path.insert(0, '.')

from provider import SportsGameOddsRESTClient, SPORTSGAMEODDS_BOOK_MAPPING, SPORTSGAMEODDS_STAT_MAPPING
from config import SPORTSGAMEODDS_API_KEY

client = SportsGameOddsRESTClient(api_key=SPORTSGAMEODDS_API_KEY)

print("Finding events with most sportsbook coverage...")
events = client.get_nba_events()

# Find event with most books
best_event = None
best_book_count = 0

for event in events:
    odds = event.get('odds', {})
    books = set()
    for odd_data in odds.values():
        for book in odd_data.get('byBookmaker', {}).keys():
            if book != 'unknown':
                books.add(book)
    if len(books) > best_book_count:
        best_book_count = len(books)
        best_event = event

if best_event:
    home = best_event.get('teams', {}).get('home', {}).get('names', {}).get('medium', 'Unknown')
    away = best_event.get('teams', {}).get('away', {}).get('names', {}).get('medium', 'Unknown')
    status = best_event.get('status', {})
    odds = best_event.get('odds', {})
    players = best_event.get('players', {})

    print(f"\nBest event: {away} @ {home}")
    print(f"Status: {status.get('displayLong', 'Unknown')}")
    print(f"Starts: {status.get('startsAt', 'Unknown')}")
    print(f"Odds: {len(odds)}, Books: {best_book_count}")

    # Get all books
    all_books = set()
    for odd_data in odds.values():
        for book in odd_data.get('byBookmaker', {}).keys():
            if book != 'unknown':
                all_books.add(book)

    # Map to our abbreviations
    us_books = ['draftkings', 'fanduel', 'betmgm', 'caesars', 'espnbet', 'fanatics',
                'betrivers', 'hardrockbet', 'ballybet', 'betparx', 'pinnacle']
    print(f"\nUS Books found:")
    for book in us_books:
        if book in all_books:
            abbrev = SPORTSGAMEODDS_BOOK_MAPPING.get(book, '??')
            print(f"  ✓ {book} ({abbrev})")
        else:
            print(f"  ✗ {book}")

    # Find a player prop with good coverage
    print(f"\nLooking for player props with 3+ US books...")
    for odd_id, odd_data in odds.items():
        parts = odd_id.split('-')
        if len(parts) >= 5:
            stat_id = parts[0]
            player_id = parts[1]
            period = parts[2]
            bet_type = parts[3]
            side = parts[4]

            if player_id not in ['all', 'home', 'away'] and period == 'game':
                by_book = odd_data.get('byBookmaker', {})
                us_book_odds = {}
                for book in us_books:
                    if book in by_book:
                        us_book_odds[book] = by_book[book]

                if len(us_book_odds) >= 3:
                    player_name = players.get(player_id, {}).get('name', player_id)
                    market = SPORTSGAMEODDS_STAT_MAPPING.get(stat_id, stat_id)
                    line = odd_data.get('fairOverUnder', 'N/A')

                    print(f"\n{player_name} {market} {side.upper()} {line}")
                    for book, data in us_book_odds.items():
                        abbrev = SPORTSGAMEODDS_BOOK_MAPPING.get(book)
                        book_odds = data.get('odds', 'N/A')
                        book_line = data.get('overUnder', '')
                        deeplink = '✓' if data.get('deeplink') else ''
                        print(f"  {abbrev}: {book_odds} @ {book_line} {deeplink}")
                    break
else:
    print("No events found with odds")
