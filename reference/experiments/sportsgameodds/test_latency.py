"""
Test SportsGameOdds REST API latency
"""
import time
import requests

API_KEY = "7546525eada0352b926e60dbc6c42cb0"
BASE_URL = "https://api.sportsgameodds.com/v2"
headers = {'x-api-key': API_KEY}

def main():
    print("=" * 60)
    print("SportsGameOdds REST API Latency Test")
    print("=" * 60)

    # Test 1: Get events endpoint (main call)
    print("\n1. GET /events?leagueID=NBA&ended=false")
    print("-" * 40)

    latencies = []
    for i in range(5):
        start = time.time()
        try:
            r = requests.get(f"{BASE_URL}/events", headers=headers,
                             params={'leagueID': 'NBA', 'ended': 'false'}, timeout=30)
            elapsed = (time.time() - start) * 1000  # ms
            latencies.append(elapsed)

            if r.status_code != 200:
                print(f"   Request {i+1}: {elapsed:.0f}ms - HTTP {r.status_code}")
                continue

            data = r.json()
            events = data.get('data', [])
            odds_count = sum(len(e.get('odds', {})) for e in events)

            print(f"   Request {i+1}: {elapsed:.0f}ms - {len(events)} events, {odds_count} odds")
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            print(f"   Request {i+1}: {elapsed:.0f}ms - Error: {e}")
        time.sleep(0.5)  # Small delay between requests

    if latencies:
        print(f"\n   Average: {sum(latencies)/len(latencies):.0f}ms")
        print(f"   Min: {min(latencies):.0f}ms")
        print(f"   Max: {max(latencies):.0f}ms")

    # Test 2: Compare data freshness
    print("\n2. Data Freshness Check")
    print("-" * 40)

    try:
        r = requests.get(f"{BASE_URL}/events", headers=headers,
                         params={'leagueID': 'NBA', 'ended': 'false'}, timeout=30)
        if r.status_code != 200:
            print(f"   HTTP {r.status_code}")
            return latencies
        data = r.json()
        events = data.get('data', [])
    except Exception as e:
        print(f"   Error: {e}")
        return latencies

    from datetime import datetime, timezone

    for event in events[:3]:
        home = event.get('teams', {}).get('home', {}).get('names', {}).get('medium', '?')
        away = event.get('teams', {}).get('away', {}).get('names', {}).get('medium', '?')
        odds = event.get('odds', {})

        # Find most recent update
        latest_update = None
        for odd_data in odds.values():
            for book_data in odd_data.get('byBookmaker', {}).values():
                updated = book_data.get('lastUpdatedAt', '')
                if updated:
                    try:
                        dt = datetime.fromisoformat(updated.replace('Z', '+00:00'))
                        if latest_update is None or dt > latest_update:
                            latest_update = dt
                    except:
                        pass

        if latest_update:
            age = (datetime.now(timezone.utc) - latest_update).total_seconds()
            print(f"   {away} @ {home}")
            print(f"   Latest update: {age:.0f}s ago ({latest_update.strftime('%H:%M:%S')} UTC)")

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    if latencies:
        avg_latency = sum(latencies)/len(latencies)
        print(f"""
REST API Latency: ~{avg_latency:.0f}ms per request

For scanning every 60-180 seconds:
- Latency is acceptable (~{avg_latency/1000:.1f}s)
- Full event data in single request
- No need to make follow-up calls

Compared to WebSocket:
- WebSocket: Real-time (<1s) but only sends eventID
- REST: ~{avg_latency:.0f}ms but gets full data

Recommendation: REST polling every 60-120s is sufficient for pre-game odds.
""")
    return latencies

if __name__ == "__main__":
    main()
