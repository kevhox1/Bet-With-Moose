"""
Find upcoming NBA games with odds
"""

import requests
import json
from datetime import datetime, timedelta

API_KEY = "7546525eada0352b926e60dbc6c42cb0"
BASE_URL = "https://api.sportsgameodds.com/v2"
headers = {'x-api-key': API_KEY}

def pp(data, max_len=3000):
    s = json.dumps(data, indent=2)
    if len(s) > max_len:
        s = s[:max_len] + "\n... (truncated)"
    print(s)

print("=" * 60)
print("Finding upcoming NBA games with odds")
print("=" * 60)

# Try different filters to find upcoming games
filters_to_try = [
    {'leagueID': 'NBA', 'status': 'scheduled'},
    {'leagueID': 'NBA', 'status': 'upcoming'},
    {'leagueID': 'NBA', 'started': 'false'},
    {'leagueID': 'NBA', 'ended': 'false'},
    {'leagueID': 'NBA', 'live': 'false', 'ended': 'false'},
    {'leagueID': 'NBA'},  # No filter, check all
]

for params in filters_to_try:
    print(f"\n--- Trying: {params} ---")
    r = requests.get(f"{BASE_URL}/events", headers=headers, params=params, timeout=30)

    if r.status_code == 200:
        data = r.json()
        events = data.get('data', [])

        # Filter for events with odds and not ended
        events_with_odds = []
        upcoming_events = []

        for e in events:
            status = e.get('status', {})
            odds = e.get('odds', {})
            has_odds = len(odds) > 0

            if not status.get('ended', True):
                upcoming_events.append(e)
                if has_odds:
                    events_with_odds.append(e)

        print(f"Total: {len(events)}, Upcoming: {len(upcoming_events)}, With odds: {len(events_with_odds)}")

        if events_with_odds:
            print("\nFound games with odds!")
            for e in events_with_odds[:3]:
                home = e.get('teams', {}).get('home', {}).get('names', {}).get('medium', 'Unknown')
                away = e.get('teams', {}).get('away', {}).get('names', {}).get('medium', 'Unknown')
                status = e.get('status', {})
                odds = e.get('odds', {})
                print(f"\n  {away} @ {home}")
                print(f"  Status: {status.get('displayLong', 'Unknown')}, Starts: {status.get('startsAt', 'Unknown')}")
                print(f"  Odds count: {len(odds)}")

                # Show one odd with bookmaker data
                if odds:
                    odd_key = list(odds.keys())[0]
                    odd = odds[odd_key]
                    by_book = odd.get('byBookmaker', {})
                    print(f"  Sample odd: {odd_key}")
                    print(f"  Bookmakers: {list(by_book.keys())}")
                    if by_book:
                        first_book = list(by_book.keys())[0]
                        print(f"  {first_book} data:")
                        pp(by_book[first_book])
            break

# If no upcoming games found, look at what we have
print("\n" + "=" * 60)
print("Checking for player props in any event")
print("=" * 60)

r = requests.get(f"{BASE_URL}/events", headers=headers, params={'leagueID': 'NBA'}, timeout=30)
if r.status_code == 200:
    data = r.json()
    events = data.get('data', [])

    for e in events:
        odds = e.get('odds', {})
        # Look for player props (contain PLAYER_ID pattern or player names)
        player_odds = {k: v for k, v in odds.items() if 'PLAYER' in k.upper() or any(x in k for x in ['points-', 'assists-', 'rebounds-', 'threes-', 'blocks-', 'steals-'])}

        if player_odds:
            home = e.get('teams', {}).get('home', {}).get('names', {}).get('medium', 'Unknown')
            away = e.get('teams', {}).get('away', {}).get('names', {}).get('medium', 'Unknown')
            print(f"\n{away} @ {home}")
            print(f"Player prop odds: {len(player_odds)}")
            print(f"Sample keys: {list(player_odds.keys())[:5]}")

            # Show one player prop
            if player_odds:
                key = list(player_odds.keys())[0]
                print(f"\nSample player prop: {key}")
                pp(player_odds[key])
            break

# Check the players field
print("\n" + "=" * 60)
print("Checking players field in events")
print("=" * 60)

for e in events[:3]:
    players = e.get('players', {})
    if players:
        home = e.get('teams', {}).get('home', {}).get('names', {}).get('medium', 'Unknown')
        away = e.get('teams', {}).get('away', {}).get('names', {}).get('medium', 'Unknown')
        print(f"\n{away} @ {home}")
        print(f"Players count: {len(players)}")
        print(f"Sample player keys: {list(players.keys())[:5]}")
        if players:
            player_key = list(players.keys())[0]
            print(f"Sample player:")
            pp(players[player_key])
        break
