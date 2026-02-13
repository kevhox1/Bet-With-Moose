"""
Deep dive into SportsGameOdds API structure
"""

import requests
import json

API_KEY = "7546525eada0352b926e60dbc6c42cb0"
BASE_URL = "https://api.sportsgameodds.com/v2"
headers = {'x-api-key': API_KEY}

def pp(data, max_len=2000):
    """Pretty print with length limit."""
    s = json.dumps(data, indent=2)
    if len(s) > max_len:
        s = s[:max_len] + "\n... (truncated)"
    print(s)

print("=" * 60)
print("1. Get NBA events with odds")
print("=" * 60)

# Get events - need to find ones with odds
r = requests.get(f"{BASE_URL}/events", headers=headers, params={
    'leagueID': 'NBA',
    'status': 'scheduled',  # Only upcoming games
}, timeout=30)

if r.status_code == 200:
    data = r.json()
    events = data.get('data', [])
    print(f"Found {len(events)} events")

    # Find an event with odds
    for event in events[:5]:
        event_id = event.get('eventID')
        odds = event.get('odds', {})
        print(f"\nEvent: {event_id}")
        print(f"  Teams: {event.get('teams', {}).get('away', {}).get('names', {}).get('medium')} @ {event.get('teams', {}).get('home', {}).get('names', {}).get('medium')}")
        print(f"  Status: {event.get('status')}")
        print(f"  Odds keys: {list(odds.keys())[:10] if odds else 'empty'}")

        if odds:
            print(f"  Sample odd:")
            first_key = list(odds.keys())[0]
            pp(odds[first_key])
            break
else:
    print(f"Error: {r.status_code} - {r.text[:500]}")

print("\n" + "=" * 60)
print("2. Get single event with full odds")
print("=" * 60)

# Get a specific event with all odds
if events:
    event_id = events[0].get('eventID')
    print(f"Fetching full event: {event_id}")

    r = requests.get(f"{BASE_URL}/events/{event_id}", headers=headers, timeout=30)
    if r.status_code == 200:
        data = r.json()
        event = data.get('data', {})
        odds = event.get('odds', {})
        print(f"Odds count: {len(odds)}")

        if odds:
            # Show structure of odds
            print("\nOdds structure:")
            for i, (key, value) in enumerate(list(odds.items())[:3]):
                print(f"\n--- Odd #{i+1}: {key} ---")
                pp(value)
    else:
        print(f"Error: {r.status_code}")

print("\n" + "=" * 60)
print("3. Available markets")
print("=" * 60)

r = requests.get(f"{BASE_URL}/markets", headers=headers, timeout=30)
if r.status_code == 200:
    data = r.json()
    markets = data.get('data', [])
    print(f"Found {len(markets)} markets")

    # Filter for player props
    player_markets = [m for m in markets if 'player' in str(m).lower()]
    print(f"\nPlayer prop markets: {len(player_markets)}")
    for m in player_markets[:20]:
        print(f"  - {m}")
else:
    print(f"Error: {r.status_code}")

print("\n" + "=" * 60)
print("4. Available sportsbooks (from odds)")
print("=" * 60)

# Collect all sportsbook IDs from odds
if events:
    all_books = set()
    for event in events:
        odds = event.get('odds', {})
        for odd_key, odd_data in odds.items():
            if isinstance(odd_data, dict):
                for key in odd_data.keys():
                    if key not in ['oddID', 'marketID', 'statEntityID', 'line', 'outcomes', 'overUnder']:
                        all_books.add(key)

    print(f"Sportsbooks found: {sorted(all_books)}")

print("\n" + "=" * 60)
print("5. Account/Usage info")
print("=" * 60)

r = requests.get(f"{BASE_URL}/account/usage", headers=headers, timeout=30)
if r.status_code == 200:
    pp(r.json())
