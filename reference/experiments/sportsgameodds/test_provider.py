"""
Test the updated SportsGameOdds provider
"""
import sys
sys.path.insert(0, '.')

from provider import SportsGameOddsRESTClient, SPORTSGAMEODDS_BOOK_MAPPING, SPORTSGAMEODDS_STAT_MAPPING
from config import SPORTSGAMEODDS_API_KEY

print("=" * 60)
print("Testing SportsGameOdds Provider")
print("=" * 60)

# Initialize client
client = SportsGameOddsRESTClient(api_key=SPORTSGAMEODDS_API_KEY)

# Test 1: Get NBA events
print("\n1. Fetching NBA events...")
events = client.get_nba_events()
print(f"   Found {len(events)} events with odds")

if events:
    # Show first event details
    event = events[0]
    home = event.get('teams', {}).get('home', {}).get('names', {}).get('medium', 'Unknown')
    away = event.get('teams', {}).get('away', {}).get('names', {}).get('medium', 'Unknown')
    odds = event.get('odds', {})
    players = event.get('players', {})

    print(f"\n   First event: {away} @ {home}")
    print(f"   Odds count: {len(odds)}")
    print(f"   Players count: {len(players)}")

    # Count player props vs team props
    player_prop_count = 0
    team_prop_count = 0
    books_found = set()

    for odd_id, odd_data in odds.items():
        by_book = odd_data.get('byBookmaker', {})
        for book in by_book.keys():
            if book != 'unknown':
                books_found.add(book)

        # Check if player prop (contains player ID)
        parts = odd_id.split('-')
        if len(parts) >= 2:
            stat_id = parts[0]
            entity_id = parts[1]
            if entity_id not in ['all', 'home', 'away']:
                player_prop_count += 1
            else:
                team_prop_count += 1

    print(f"   Player props: {player_prop_count}")
    print(f"   Team props: {team_prop_count}")
    print(f"   Books found: {len(books_found)}")

    # Map books to our abbreviations
    mapped_books = []
    unmapped_books = []
    for book in sorted(books_found):
        abbrev = SPORTSGAMEODDS_BOOK_MAPPING.get(book)
        if abbrev:
            mapped_books.append(f"{book}={abbrev}")
        else:
            unmapped_books.append(book)

    print(f"\n   Mapped books: {', '.join(mapped_books[:15])}")
    if len(mapped_books) > 15:
        print(f"   ... and {len(mapped_books) - 15} more")
    if unmapped_books:
        print(f"   Unmapped books: {', '.join(unmapped_books)}")

    # Show sample player prop with multiple books
    print("\n2. Sample player prop with odds...")
    for odd_id, odd_data in odds.items():
        parts = odd_id.split('-')
        if len(parts) >= 5:
            stat_id = parts[0]
            player_id = parts[1]
            if player_id not in ['all', 'home', 'away'] and stat_id in SPORTSGAMEODDS_STAT_MAPPING:
                by_book = odd_data.get('byBookmaker', {})
                us_books = {k: v for k, v in by_book.items()
                           if SPORTSGAMEODDS_BOOK_MAPPING.get(k) in ['DK', 'FD', 'MG', 'CZ', 'ES', 'PN']}
                if len(us_books) >= 2:
                    # Get player name
                    player_name = players.get(player_id, {}).get('name', player_id)
                    market = SPORTSGAMEODDS_STAT_MAPPING.get(stat_id, stat_id)
                    line = odd_data.get('bookOverUnder', odd_data.get('fairOverUnder', 'N/A'))
                    side = parts[4] if len(parts) > 4 else 'N/A'

                    print(f"   {player_name} - {market} {side} {line}")
                    print(f"   Odds by book:")
                    for book, book_data in us_books.items():
                        abbrev = SPORTSGAMEODDS_BOOK_MAPPING.get(book, book)
                        odds_val = book_data.get('odds', 'N/A')
                        link = book_data.get('deeplink', '')
                        link_status = '✓ deeplink' if link else ''
                        print(f"      {abbrev}: {odds_val} {link_status}")
                    break

# Test 2: Check account usage
print("\n3. Account usage...")
usage = client.get_account_usage()
if usage and 'data' in usage:
    data = usage['data']
    rate_limits = data.get('rateLimits', {})
    per_hour = rate_limits.get('per-hour', {})
    print(f"   Tier: {data.get('tier')}")
    print(f"   Requests this hour: {per_hour.get('current-requests')}/{per_hour.get('max-requests')}")

print("\n✓ Provider test complete!")
