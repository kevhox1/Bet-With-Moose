#!/usr/bin/env python3
"""
Bolt Odds NBA Stream Test

Connects to WebSocket, subscribes to NBA data, and analyzes the response structure.
"""

import asyncio
import json
import time
from datetime import datetime

try:
    import websockets
except ImportError:
    print("ERROR: pip install websockets")
    exit(1)

API_KEY = "24ad4285-3c06-4a2a-bc86-77d67ab1cec0"
WS_URL = f"wss://spro.agency/api?key={API_KEY}"


async def stream_nba_odds(duration: int = 60, save_sample: bool = True):
    """Stream NBA odds and analyze the data structure."""
    print("\n" + "="*80)
    print("BOLT ODDS NBA LIVE STREAM TEST")
    print("="*80)
    print(f"Duration: {duration} seconds")
    print(f"Started: {datetime.now().isoformat()}")
    print("="*80 + "\n")

    all_messages = []
    update_count = 0
    latencies = []

    try:
        connect_start = time.time()
        async with websockets.connect(WS_URL) as ws:
            connect_time = (time.time() - connect_start) * 1000
            print(f"[CONNECT] Connected in {connect_time:.1f}ms")

            # Wait for connection ack
            msg = await ws.recv()
            data = json.loads(msg)
            print(f"[ACK] {data}")

            # Send subscription
            subscription = {"action": "subscribe", "sports": ["NBA"]}
            await ws.send(json.dumps(subscription))
            print(f"[SUBSCRIBE] Sent: {subscription}")

            # Listen for data
            start = time.time()
            initial_state_received = False

            while (time.time() - start) < duration:
                try:
                    recv_start = time.time()
                    msg = await asyncio.wait_for(ws.recv(), timeout=10)
                    recv_latency = (time.time() - recv_start) * 1000

                    data = json.loads(msg)
                    all_messages.append(data)
                    action = data.get('action', 'unknown')

                    if action == 'ping':
                        continue

                    elif action == 'initial_state':
                        initial_state_received = True
                        print(f"\n[INITIAL_STATE] Received! Size: {len(msg)} bytes")

                        # Analyze structure
                        if isinstance(data.get('data'), list):
                            print(f"  Data is a LIST with {len(data['data'])} items")
                            if data['data']:
                                print("\n  First item structure:")
                                print(json.dumps(data['data'][0], indent=4)[:2000])

                                # Analyze all items
                                print(f"\n  All sports in data:")
                                sports = set()
                                books = set()
                                games = set()
                                markets = set()

                                for item in data['data']:
                                    if isinstance(item, dict):
                                        sports.add(item.get('sport', 'unknown'))
                                        books.add(item.get('sportsbook', 'unknown'))
                                        games.add(item.get('game', 'unknown'))
                                        for key in item.keys():
                                            if key not in ['sport', 'sportsbook', 'game', 'universal_id', 'when', 'timestamp']:
                                                markets.add(key)

                                print(f"    Sports: {sports}")
                                print(f"    Books: {books}")
                                print(f"    Games ({len(games)}): {list(games)[:3]}...")
                                print(f"    Market keys: {markets}")

                        elif isinstance(data.get('data'), dict):
                            print(f"  Data is a DICT with {len(data['data'])} keys")
                            print(f"  Keys: {list(data['data'].keys())[:5]}")

                        else:
                            print(f"  Data structure: {type(data.get('data'))}")
                            print(f"  Raw: {str(data)[:1000]}")

                    elif action in ('game_update', 'line_update'):
                        update_count += 1
                        latencies.append(recv_latency)
                        game = data.get('game', 'unknown')[:50]
                        book = data.get('sportsbook', 'unknown')
                        elapsed = time.time() - start
                        print(f"[{elapsed:6.1f}s] {action}: {game} ({book}) - {len(msg)} bytes, {recv_latency:.0f}ms")

                        # Show first update in detail
                        if update_count == 1:
                            print("\n  First update structure:")
                            print(json.dumps(data, indent=2)[:3000])
                            print()

                    elif action == 'subscription_updated':
                        print(f"[SUBSCRIPTION] {data}")

                    else:
                        print(f"[{action}] {str(data)[:200]}")

                except asyncio.TimeoutError:
                    print(".", end="", flush=True)
                    continue

    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")

    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"  Total messages: {len(all_messages)}")
    print(f"  Updates received: {update_count}")
    print(f"  Initial state: {'Yes' if initial_state_received else 'No'}")

    if latencies:
        print(f"  Avg update latency: {sum(latencies)/len(latencies):.1f}ms")
        print(f"  Min latency: {min(latencies):.1f}ms")
        print(f"  Max latency: {max(latencies):.1f}ms")

    # Save sample data
    if save_sample and all_messages:
        sample_file = "/home/user/NBA-Long-Shot-Scanner-Bot/tests/bolt_odds/sample_data.json"
        with open(sample_file, 'w') as f:
            json.dump(all_messages[:20], f, indent=2)
        print(f"\n  Sample data saved to: {sample_file}")

    return all_messages


if __name__ == "__main__":
    import sys
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 45
    asyncio.run(stream_nba_odds(duration=duration))
