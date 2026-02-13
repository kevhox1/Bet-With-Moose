#!/usr/bin/env python3
"""
Fetch NBA odds directly via WebSocket with proper parsing.

This script connects, subscribes, and parses the full initial state for NBA.
"""

import asyncio
import json
from datetime import datetime
from collections import defaultdict

try:
    import websockets
except ImportError:
    print("ERROR: pip install websockets")
    exit(1)

API_KEY = "24ad4285-3c06-4a2a-bc86-77d67ab1cec0"
WS_URL = f"wss://spro.agency/api?key={API_KEY}"


async def fetch_nba_odds():
    """Fetch NBA odds and analyze available markets."""
    print("\n" + "="*80)
    print("FETCHING NBA ODDS FROM BOLT ODDS")
    print("="*80)

    # Storage
    games = defaultdict(lambda: defaultdict(dict))  # game -> book -> outcomes
    markets_by_book = defaultdict(set)
    all_sportsbooks = set()
    all_games = set()

    try:
        async with websockets.connect(WS_URL, max_size=50*1024*1024) as ws:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Connected")

            # Wait for ack
            msg = await ws.recv()
            print(f"[ACK] {json.loads(msg)}")

            # Subscribe to NBA only
            await ws.send(json.dumps({"action": "subscribe", "sports": ["NBA"]}))
            print("[SUBSCRIBE] Sent NBA subscription")

            # Collect messages for 30 seconds
            start = asyncio.get_event_loop().time()
            msg_count = 0
            nba_msg_count = 0

            while (asyncio.get_event_loop().time() - start) < 30:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    data = json.loads(msg)
                    action = data.get('action', 'unknown')
                    msg_count += 1

                    if action == 'ping':
                        continue

                    if action == 'initial_state':
                        sport = data.get('data', {}).get('sport', data.get('sport', 'unknown'))
                        if sport == 'NBA':
                            nba_msg_count += 1
                            book = data.get('data', {}).get('sportsbook', 'unknown')
                            game = data.get('data', {}).get('game', 'unknown')
                            outcomes = data.get('data', {}).get('outcomes', {})

                            all_sportsbooks.add(book)
                            all_games.add(game)

                            # Parse outcomes
                            for outcome_key, outcome_data in outcomes.items():
                                market_name = outcome_data.get('outcome_name', 'unknown')
                                markets_by_book[book].add(market_name)
                                games[game][book][outcome_key] = outcome_data

                            print(f"  NBA: {book} | {game} | {len(outcomes)} outcomes")

                    elif action in ('line_update', 'game_update'):
                        # Check if NBA
                        sport = data.get('data', {}).get('sport', 'unknown')
                        if sport == 'NBA':
                            nba_msg_count += 1
                            book = data.get('data', {}).get('sportsbook', 'unknown')
                            game = data.get('data', {}).get('game', 'unknown')
                            print(f"  UPDATE: {book} | {game}")

                except asyncio.TimeoutError:
                    print(".", end="", flush=True)
                    continue

    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")

    # Summary
    print("\n" + "="*80)
    print("NBA DATA SUMMARY")
    print("="*80)

    print(f"\nTotal messages: {msg_count}")
    print(f"NBA messages: {nba_msg_count}")

    print(f"\n📚 Sportsbooks with NBA data ({len(all_sportsbooks)}):")
    for book in sorted(all_sportsbooks):
        print(f"  - {book}")

    print(f"\n🏀 NBA Games ({len(all_games)}):")
    for game in sorted(all_games):
        print(f"  - {game}")

    print(f"\n📈 Markets by Sportsbook:")
    for book, markets in sorted(markets_by_book.items()):
        print(f"\n  {book} ({len(markets)} markets):")
        for m in sorted(markets):
            print(f"    - {m}")

    # Save sample game data
    if games:
        sample_game = list(games.keys())[0]
        sample_file = "/home/user/NBA-Long-Shot-Scanner-Bot/tests/bolt_odds/nba_game_sample.json"
        with open(sample_file, 'w') as f:
            json.dump({sample_game: dict(games[sample_game])}, f, indent=2, default=str)
        print(f"\n💾 Sample game data saved to: {sample_file}")

    return games, markets_by_book


if __name__ == "__main__":
    asyncio.run(fetch_nba_odds())
