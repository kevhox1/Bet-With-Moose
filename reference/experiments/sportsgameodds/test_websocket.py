"""
Test SportsGameOdds WebSocket Streaming
=======================================

Based on Stuart's email:
- WebSocket sends only eventID when an event changes
- Need to make REST request to get full updated event
- 10 concurrent streams allowed

What "10 concurrent streams" means:
-----------------------------------
A "stream" is a WebSocket subscription to a specific channel/topic.

With 10 concurrent streams, you can subscribe to:
- 10 individual events (games) at once, OR
- 10 different leagues at once, OR
- Some combination

For NBA scanning:
- If you subscribe to "NBA" as one stream, you get updates for ALL NBA games
- That's only 1 stream, leaving 9 more for other sports/leagues
- OR you could subscribe to 10 specific NBA games individually

The flow:
1. Connect to WebSocket
2. Subscribe to NBA (or specific events)
3. Receive eventID when odds change
4. Make REST call to get full event data
5. Process and alert on +EV opportunities
"""

import asyncio
import json
import time
import requests

API_KEY = "7546525eada0352b926e60dbc6c42cb0"
REST_BASE_URL = "https://api.sportsgameodds.com/v2"

# Try different WebSocket URLs (need to confirm actual URL)
WS_URLS_TO_TRY = [
    f"wss://api.sportsgameodds.com/v2/stream?apiKey={API_KEY}",
    f"wss://ws.sportsgameodds.com/v2?apiKey={API_KEY}",
    f"wss://stream.sportsgameodds.com?apiKey={API_KEY}",
    f"wss://api.sportsgameodds.com/stream?x-api-key={API_KEY}",
]

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    print("Install websockets: pip install websockets")

async def test_websocket_connection(url: str, timeout: int = 10):
    """Test a single WebSocket URL."""
    print(f"\n🔌 Trying: {url[:60]}...")

    try:
        async with websockets.connect(url, close_timeout=5) as ws:
            print(f"   ✓ Connected!")

            # Try to subscribe to NBA
            subscribe_msg = {
                "action": "subscribe",
                "league": "NBA"
            }
            await ws.send(json.dumps(subscribe_msg))
            print(f"   → Sent subscribe message")

            # Wait for response
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=timeout)
                print(f"   ← Received: {response[:200]}...")
                return True, response
            except asyncio.TimeoutError:
                print(f"   ⏱️ No response within {timeout}s")
                return True, "Connected but no response"

    except websockets.exceptions.InvalidStatusCode as e:
        print(f"   ✗ HTTP {e.status_code}")
        return False, str(e)
    except Exception as e:
        print(f"   ✗ Error: {type(e).__name__}: {e}")
        return False, str(e)

async def main():
    print("=" * 60)
    print("SportsGameOdds WebSocket Test")
    print("=" * 60)

    print("\n📚 What '10 concurrent streams' means:")
    print("-" * 40)
    print("• A 'stream' = one WebSocket subscription")
    print("• You can have 10 active subscriptions at once")
    print("• Options:")
    print("  - Subscribe to 'NBA' = 1 stream (all NBA games)")
    print("  - Subscribe to 10 specific games = 10 streams")
    print("  - Mix: NBA + NHL + MLB = 3 streams")
    print("")
    print("• When odds change, you get eventID only")
    print("• Then make REST call to get full event data")

    if not WEBSOCKETS_AVAILABLE:
        print("\n❌ websockets library not installed")
        print("   Run: pip install websockets")
        return

    print("\n" + "=" * 60)
    print("Testing WebSocket Connections")
    print("=" * 60)

    # First, let's check the API docs endpoint for WebSocket info
    print("\n🔍 Checking API for WebSocket endpoint info...")
    headers = {'x-api-key': API_KEY}

    # Try to find WebSocket info
    endpoints_to_check = [
        '/stream',
        '/websocket',
        '/realtime',
        '/subscribe',
    ]

    for endpoint in endpoints_to_check:
        try:
            r = requests.get(f"{REST_BASE_URL}{endpoint}", headers=headers, timeout=10)
            if r.status_code != 404:
                print(f"   {endpoint}: {r.status_code}")
                if r.status_code == 200:
                    print(f"   Response: {r.text[:200]}")
        except Exception as e:
            pass

    # Test WebSocket URLs
    print("\n🔌 Testing WebSocket URLs...")
    for url in WS_URLS_TO_TRY:
        success, result = await test_websocket_connection(url)
        if success and "Connected" in str(result):
            print(f"\n✓ Found working WebSocket endpoint!")
            break

    print("\n" + "=" * 60)
    print("Recommendation")
    print("=" * 60)
    print("""
Based on Stuart's email, the WebSocket:
1. Connects with same API key
2. Sends eventID when odds change
3. You then call REST API to get full event

For production use:
1. Maintain WebSocket connection
2. On eventID received, call GET /events/{eventID}
3. Process odds and check for +EV
4. Send alerts

For now, the REST polling approach works well:
- Poll every 60-180 seconds
- Full event data in one call
- Simpler to implement
    """)

if __name__ == "__main__":
    asyncio.run(main())
