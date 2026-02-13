#!/usr/bin/env python3
"""
Bolt Odds Latency & Alternate Lines Test

Tests:
1. How frequently do odds updates come through? (latency/freshness)
2. Are alternate lines available (multiple lines per player per market)?
"""

import asyncio
import json
import time
from datetime import datetime
from collections import defaultdict

try:
    import websockets
except ImportError:
    print("ERROR: pip install websockets")
    exit(1)

API_KEY = "24ad4285-3c06-4a2a-bc86-77d67ab1cec0"
WS_URL = f"wss://spro.agency/api?key={API_KEY}"


async def test_latency_and_alternates(duration: int = 120):
    """
    Test update frequency and check for alternate lines.

    TheOddsAPI has 60 second latency - we want to beat that.
    """
    print("\n" + "="*80)
    print("BOLT ODDS LATENCY & ALTERNATE LINES TEST")
    print("="*80)
    print(f"Duration: {duration} seconds")
    print(f"Comparison: TheOddsAPI latency is ~60 seconds")
    print("="*80 + "\n")

    # Track updates
    update_times = []
    update_types = defaultdict(int)

    # Track player lines to check for alternates
    player_lines = defaultdict(lambda: defaultdict(list))  # player -> market -> [lines]

    # Track by sportsbook
    updates_by_book = defaultdict(int)

    try:
        async with websockets.connect(WS_URL, max_size=50*1024*1024) as ws:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Connected")

            # Wait for ack
            msg = await ws.recv()
            print(f"[ACK] {json.loads(msg)}")

            # Subscribe to NBA
            await ws.send(json.dumps({"action": "subscribe", "sports": ["NBA"]}))
            print("[SUBSCRIBE] Sent NBA subscription\n")

            # Collect data
            start = time.time()
            initial_state_count = 0
            line_update_count = 0
            last_update_time = time.time()

            print("Listening for updates...\n")
            print(f"{'Time':>8} | {'Type':>15} | {'Sportsbook':>15} | {'Details'}")
            print("-" * 80)

            while (time.time() - start) < duration:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    now = time.time()
                    data = json.loads(msg)
                    action = data.get('action', 'unknown')

                    if action == 'ping':
                        continue

                    # Record update time
                    update_times.append(now)
                    update_types[action] += 1

                    elapsed = now - start
                    time_since_last = now - last_update_time
                    last_update_time = now

                    if action == 'initial_state':
                        initial_state_count += 1
                        sport = data.get('data', {}).get('sport', 'unknown')
                        book = data.get('data', {}).get('sportsbook', 'unknown')
                        game = data.get('data', {}).get('game', 'unknown')[:30]
                        outcomes = data.get('data', {}).get('outcomes', {})

                        if sport == 'NBA':
                            updates_by_book[book] += 1

                            # Parse outcomes for alternate lines
                            for key, val in outcomes.items():
                                target = val.get('outcome_target')
                                market = val.get('outcome_name')
                                line = val.get('outcome_line')
                                over_under = val.get('outcome_over_under')

                                if target and market and line:
                                    player_lines[target][market].append({
                                        'line': line,
                                        'over_under': over_under,
                                        'book': book
                                    })

                            print(f"{elapsed:7.1f}s | {'initial_state':>15} | {book:>15} | {game} ({len(outcomes)} outcomes)")

                    elif action == 'line_update':
                        line_update_count += 1
                        sport = data.get('data', {}).get('sport', 'unknown')
                        book = data.get('data', {}).get('sportsbook', 'unknown')
                        game = data.get('data', {}).get('game', 'unknown')[:30]

                        if sport == 'NBA':
                            updates_by_book[book] += 1
                            print(f"{elapsed:7.1f}s | {'line_update':>15} | {book:>15} | {game} (+{time_since_last:.1f}s)")

                    elif action == 'game_update':
                        sport = data.get('data', {}).get('sport', 'unknown')
                        book = data.get('data', {}).get('sportsbook', 'unknown')
                        game = data.get('data', {}).get('game', 'unknown')[:30]

                        if sport == 'NBA':
                            updates_by_book[book] += 1
                            print(f"{elapsed:7.1f}s | {'game_update':>15} | {book:>15} | {game}")

                except asyncio.TimeoutError:
                    continue

    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")

    # Analysis
    print("\n" + "="*80)
    print("LATENCY ANALYSIS")
    print("="*80)

    if len(update_times) > 1:
        intervals = [update_times[i+1] - update_times[i] for i in range(len(update_times)-1)]
        intervals = [i for i in intervals if i > 0.1]  # Filter out rapid-fire initial state

        if intervals:
            avg_interval = sum(intervals) / len(intervals)
            min_interval = min(intervals)
            max_interval = max(intervals)

            print(f"\nUpdate Frequency (excluding initial burst):")
            print(f"  Average interval: {avg_interval:.2f} seconds")
            print(f"  Min interval: {min_interval:.2f} seconds")
            print(f"  Max interval: {max_interval:.2f} seconds")
            print(f"  Total updates: {len(update_times)}")

            print(f"\n  ** TheOddsAPI latency: ~60 seconds **")
            if avg_interval < 60:
                print(f"  ** Bolt Odds is {60/avg_interval:.1f}x FASTER! **")

    print(f"\nUpdates by Type:")
    for t, count in sorted(update_types.items()):
        print(f"  {t}: {count}")

    print(f"\nUpdates by Sportsbook (NBA only):")
    for book, count in sorted(updates_by_book.items(), key=lambda x: -x[1]):
        print(f"  {book}: {count}")

    # Alternate lines analysis
    print("\n" + "="*80)
    print("ALTERNATE LINES ANALYSIS")
    print("="*80)
    print("\nLooking for players with MULTIPLE lines per market (alternates)...")

    # Find players with multiple lines
    alternates_found = defaultdict(list)

    for player, markets in player_lines.items():
        for market, lines in markets.items():
            # Get unique lines
            unique_lines = set()
            for l in lines:
                unique_lines.add((l['line'], l['over_under']))

            if len(unique_lines) > 1:
                alternates_found[market].append({
                    'player': player,
                    'lines': sorted(unique_lines, key=lambda x: float(x[0]) if x[0] else 0)
                })

    if alternates_found:
        print("\n✅ ALTERNATE LINES FOUND!\n")

        # Map TheOddsAPI market names
        market_mapping = {
            'Points': 'player_points_alternate',
            'Rebounds': 'player_rebounds_alternate',
            'Assists': 'player_assists_alternate',
            'Threes': 'player_threes_alternate',
            'Blocks': 'player_blocks_alternate',
            'Steals': 'player_steals_alternate',
        }

        for market, players in sorted(alternates_found.items()):
            theodds_equiv = market_mapping.get(market, 'N/A')
            print(f"\n📊 {market} (TheOddsAPI: {theodds_equiv})")
            print(f"   Players with multiple lines: {len(players)}")

            # Show sample
            for p in players[:3]:
                lines_str = ", ".join([f"{l[1]} {l[0]}" if l[1] else str(l[0]) for l in p['lines'][:5]])
                print(f"   • {p['player']}: {lines_str}{'...' if len(p['lines']) > 5 else ''}")
    else:
        print("\n❌ No alternate lines found in sample data")
        print("   This could mean:")
        print("   1. Data format is different than expected")
        print("   2. Need longer sample time")
        print("   3. Alternates not available on this plan")

    # Summary comparison
    print("\n" + "="*80)
    print("COMPARISON TO THEODDSAPI MARKETS")
    print("="*80)

    theodds_markets = [
        ('player_double_double', 'Double-Doubles'),
        ('player_triple_double', 'Triple-Doubles'),
        ('player_first_basket', 'First Basket'),
        ('player_first_team_basket', 'First Team Basket'),
        ('player_points_alternate', 'Points (alternates)'),
        ('player_rebounds_alternate', 'Rebounds (alternates)'),
        ('player_assists_alternate', 'Assists (alternates)'),
        ('player_blocks_alternate', 'Blocks (alternates)'),
        ('player_steals_alternate', 'Steals (alternates)'),
        ('player_threes_alternate', 'Threes (alternates)'),
    ]

    # Check what we found
    all_markets = set()
    for player, markets in player_lines.items():
        all_markets.update(markets.keys())

    print(f"\nMarkets found in Bolt Odds data: {sorted(all_markets)}\n")

    print("TheOddsAPI Market               | Bolt Odds Equivalent | Status")
    print("-" * 70)

    bolt_to_theodds = {
        'Double-Doubles': 'Double-Doubles',
        'Triple-Doubles': 'Triple-Doubles',
        'First Basket': 'First Basket',
        'First Team Basket': 'First Team Basket',
        'Points': 'Points',
        'Rebounds': 'Rebounds',
        'Assists': 'Assists',
        'Blocks': 'Blocks',
        'Steals': 'Steals',
        'Threes': 'Threes',
    }

    for theodds, display in theodds_markets:
        # Find matching Bolt Odds market
        bolt_market = None
        for m in all_markets:
            if display.replace(' (alternates)', '') in m:
                bolt_market = m
                break

        if bolt_market:
            has_alternates = bolt_market in alternates_found and len(alternates_found[bolt_market]) > 0
            status = "✅ Available" + (" + Alternates" if has_alternates else "")
        else:
            status = "❓ Not in sample"

        print(f"{theodds:30} | {bolt_market or 'N/A':20} | {status}")


if __name__ == "__main__":
    import sys
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    asyncio.run(test_latency_and_alternates(duration=duration))
