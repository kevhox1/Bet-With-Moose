#!/usr/bin/env python3
"""
Bolt Odds WebSocket Subscription Test

Tests different subscription message formats to receive odds data.
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


async def test_subscription(subscription_msg: dict, duration: int = 20):
    """Test a specific subscription message format."""
    print(f"\n{'='*70}")
    print(f"Testing subscription: {json.dumps(subscription_msg)}")
    print(f"{'='*70}")

    messages = []

    try:
        async with websockets.connect(WS_URL) as ws:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Connected")

            # Wait for connection ack
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(msg)
            print(f"  <- {data}")

            # Send subscription
            print(f"  -> Sending: {subscription_msg}")
            await ws.send(json.dumps(subscription_msg))

            # Listen for responses
            start = time.time()
            while (time.time() - start) < duration:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    data = json.loads(msg)
                    messages.append(data)

                    # Print summary of message
                    action = data.get('action', data.get('type', 'unknown'))
                    size = len(msg)

                    if action == 'ping':
                        print(f"  <- ping")
                    elif action == 'initial_state':
                        # This is what we want!
                        games = list(data.get('data', {}).keys())[:3]
                        print(f"  <- INITIAL_STATE! Games: {len(data.get('data', {}))} - Sample: {games}")
                        # Print first game's data structure
                        if data.get('data'):
                            first_game = list(data['data'].keys())[0]
                            game_data = data['data'][first_game]
                            print(f"     First game structure: {list(game_data.keys())[:10]}")
                    elif action in ('game_update', 'line_update'):
                        game = data.get('game', 'unknown')[:40]
                        print(f"  <- {action}: {game} ({size} bytes)")
                    elif action == 'subscription_updated':
                        print(f"  <- subscription_updated: {data}")
                    else:
                        print(f"  <- {action}: {str(data)[:100]}")

                except asyncio.TimeoutError:
                    continue

    except Exception as e:
        print(f"  ERROR: {e}")

    return messages


async def main():
    print("#"*70)
    print("# BOLT ODDS SUBSCRIPTION FORMAT TESTING")
    print("#"*70)

    # Test 1: Simple sports array
    await test_subscription(
        {"sports": ["NBA"]},
        duration=15
    )

    # Test 2: With sportsbooks
    await test_subscription(
        {"sports": ["NBA"], "sportsbooks": ["draftkings", "fanduel"]},
        duration=15
    )

    # Test 3: All data (no filter)
    await test_subscription(
        {},
        duration=15
    )

    # Test 4: Subscribe action format
    await test_subscription(
        {"action": "subscribe", "sports": ["NBA"]},
        duration=15
    )

    # Test 5: Different message format from docs
    await test_subscription(
        {"type": "subscribe", "filters": {"sports": ["NBA"]}},
        duration=10
    )

    print("\n" + "#"*70)
    print("# DONE")
    print("#"*70)


if __name__ == "__main__":
    asyncio.run(main())
