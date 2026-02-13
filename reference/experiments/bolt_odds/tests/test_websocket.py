#!/usr/bin/env python3
"""
Bolt Odds WebSocket Connection Tester

Tests the WebSocket connection for:
- Connection establishment
- Initial state reception
- Real-time update latency
- Message format analysis

Usage: python test_websocket.py [--duration SECONDS] [--sport SPORT]
"""

import asyncio
import json
import time
import argparse
from datetime import datetime
from collections import defaultdict

try:
    import websockets
except ImportError:
    print("ERROR: websockets library not installed")
    print("Install with: pip install websockets")
    exit(1)

# Bolt Odds API configuration
API_KEY = "24ad4285-3c06-4a2a-bc86-77d67ab1cec0"
WS_URL = f"wss://spro.agency/api?key={API_KEY}"
PLAYBYPLAY_URL = f"wss://spro.agency/api/playbyplay?key={API_KEY}"


class LatencyTracker:
    """Track and analyze message latency."""

    def __init__(self):
        self.connection_time = None
        self.first_message_time = None
        self.message_times = []
        self.message_types = defaultdict(int)
        self.message_sizes = []

    def record_connection(self):
        self.connection_time = time.time()

    def record_message(self, msg_type: str, msg_size: int):
        now = time.time()
        if self.first_message_time is None:
            self.first_message_time = now
        self.message_times.append(now)
        self.message_types[msg_type] += 1
        self.message_sizes.append(msg_size)

    def get_stats(self) -> dict:
        if not self.message_times:
            return {"error": "No messages received"}

        intervals = []
        for i in range(1, len(self.message_times)):
            intervals.append(self.message_times[i] - self.message_times[i-1])

        return {
            "time_to_first_message_ms": (self.first_message_time - self.connection_time) * 1000 if self.connection_time else None,
            "total_messages": len(self.message_times),
            "message_types": dict(self.message_types),
            "avg_message_interval_ms": (sum(intervals) / len(intervals) * 1000) if intervals else None,
            "min_interval_ms": min(intervals) * 1000 if intervals else None,
            "max_interval_ms": max(intervals) * 1000 if intervals else None,
            "avg_message_size_bytes": sum(self.message_sizes) / len(self.message_sizes) if self.message_sizes else None,
            "total_data_bytes": sum(self.message_sizes),
        }


async def test_websocket_connection(
    duration_seconds: int = 30,
    sport_filter: str = None,
    sportsbook_filter: str = None,
    verbose: bool = True
):
    """
    Test WebSocket connection and measure latency.

    Args:
        duration_seconds: How long to listen for messages
        sport_filter: Filter to specific sport (e.g., "NBA")
        sportsbook_filter: Filter to specific sportsbook (e.g., "DraftKings")
        verbose: Print each message
    """
    tracker = LatencyTracker()
    sample_messages = []

    print("\n" + "="*80)
    print("BOLT ODDS WEBSOCKET CONNECTION TEST")
    print("="*80)
    print(f"URL: {WS_URL[:50]}...")
    print(f"Duration: {duration_seconds} seconds")
    print(f"Sport filter: {sport_filter or 'ALL'}")
    print(f"Sportsbook filter: {sportsbook_filter or 'ALL'}")
    print("="*80)

    try:
        print(f"\n[{datetime.now().isoformat()}] Connecting to WebSocket...")
        connect_start = time.time()

        async with websockets.connect(WS_URL) as websocket:
            connect_time = (time.time() - connect_start) * 1000
            tracker.record_connection()
            print(f"[{datetime.now().isoformat()}] ✅ Connected! (took {connect_time:.2f}ms)")

            # Send subscription filter if specified
            if sport_filter or sportsbook_filter:
                subscription = {}
                if sport_filter:
                    subscription['sports'] = [sport_filter]
                if sportsbook_filter:
                    subscription['sportsbooks'] = [sportsbook_filter]

                print(f"[{datetime.now().isoformat()}] Sending subscription filter: {subscription}")
                await websocket.send(json.dumps(subscription))

            # Listen for messages
            start_time = time.time()
            print(f"\n[{datetime.now().isoformat()}] Listening for messages...\n")

            while (time.time() - start_time) < duration_seconds:
                try:
                    # Set timeout to check duration periodically
                    message = await asyncio.wait_for(
                        websocket.recv(),
                        timeout=min(5.0, duration_seconds - (time.time() - start_time))
                    )

                    msg_size = len(message)
                    try:
                        data = json.loads(message)
                        msg_type = data.get('type', data.get('action', 'unknown'))

                        # Handle different message structures
                        if isinstance(data, dict):
                            if 'type' in data:
                                msg_type = data['type']
                            elif 'action' in data:
                                msg_type = data['action']
                            elif 'event' in data:
                                msg_type = data['event']
                            else:
                                msg_type = list(data.keys())[0] if data else 'empty'
                    except json.JSONDecodeError:
                        msg_type = 'non_json'
                        data = message

                    tracker.record_message(msg_type, msg_size)

                    # Store sample messages
                    if len(sample_messages) < 5 or msg_type not in [m.get('type') for m in sample_messages if isinstance(m, dict)]:
                        sample_messages.append(data)

                    if verbose:
                        elapsed = time.time() - start_time
                        preview = str(data)[:200] + "..." if len(str(data)) > 200 else str(data)
                        print(f"[{elapsed:6.2f}s] {msg_type:20s} ({msg_size:6d} bytes): {preview}")

                except asyncio.TimeoutError:
                    continue

            print(f"\n[{datetime.now().isoformat()}] Test duration completed.")

    except websockets.exceptions.ConnectionClosed as e:
        print(f"\n❌ Connection closed: {e}")
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")

    # Print statistics
    stats = tracker.get_stats()
    print("\n" + "="*80)
    print("LATENCY & PERFORMANCE STATISTICS")
    print("="*80)

    for key, value in stats.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}")
        elif isinstance(value, dict):
            print(f"  {key}:")
            for k, v in value.items():
                print(f"    - {k}: {v}")
        else:
            print(f"  {key}: {value}")

    # Print sample messages
    print("\n" + "="*80)
    print("SAMPLE MESSAGES (for structure analysis)")
    print("="*80)

    for i, msg in enumerate(sample_messages[:5]):
        print(f"\n--- Sample {i+1} ---")
        print(json.dumps(msg, indent=2, default=str)[:2000])

    return stats, sample_messages


async def test_playbyplay_connection(duration_seconds: int = 15):
    """Test the play-by-play WebSocket endpoint."""
    print("\n" + "="*80)
    print("BOLT ODDS PLAY-BY-PLAY WEBSOCKET TEST")
    print("="*80)
    print(f"URL: {PLAYBYPLAY_URL[:50]}...")
    print(f"Duration: {duration_seconds} seconds")
    print("="*80)

    tracker = LatencyTracker()

    try:
        print(f"\n[{datetime.now().isoformat()}] Connecting to Play-by-Play WebSocket...")
        connect_start = time.time()

        async with websockets.connect(PLAYBYPLAY_URL) as websocket:
            connect_time = (time.time() - connect_start) * 1000
            tracker.record_connection()
            print(f"[{datetime.now().isoformat()}] ✅ Connected! (took {connect_time:.2f}ms)")

            start_time = time.time()
            print(f"\n[{datetime.now().isoformat()}] Listening for play-by-play data...\n")

            while (time.time() - start_time) < duration_seconds:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    data = json.loads(message)
                    msg_type = data.get('type', data.get('event', 'unknown'))
                    tracker.record_message(msg_type, len(message))

                    elapsed = time.time() - start_time
                    preview = str(data)[:150] + "..." if len(str(data)) > 150 else str(data)
                    print(f"[{elapsed:6.2f}s] {msg_type}: {preview}")

                except asyncio.TimeoutError:
                    continue

    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")

    stats = tracker.get_stats()
    print("\n" + "="*80)
    print("PLAY-BY-PLAY STATISTICS")
    print("="*80)
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Test Bolt Odds WebSocket connection")
    parser.add_argument("--duration", type=int, default=30, help="Test duration in seconds")
    parser.add_argument("--sport", type=str, default=None, help="Sport filter (e.g., NBA)")
    parser.add_argument("--sportsbook", type=str, default=None, help="Sportsbook filter (e.g., DraftKings)")
    parser.add_argument("--quiet", action="store_true", help="Reduce output verbosity")
    parser.add_argument("--playbyplay", action="store_true", help="Test play-by-play endpoint instead")
    args = parser.parse_args()

    print("\n" + "#"*80)
    print("#" + " "*25 + "BOLT ODDS WEBSOCKET TESTER" + " "*27 + "#")
    print("#" + " "*22 + f"Run at: {datetime.now().isoformat()}" + " "*20 + "#")
    print("#"*80)

    if args.playbyplay:
        asyncio.run(test_playbyplay_connection(args.duration))
    else:
        asyncio.run(test_websocket_connection(
            duration_seconds=args.duration,
            sport_filter=args.sport,
            sportsbook_filter=args.sportsbook,
            verbose=not args.quiet
        ))


if __name__ == "__main__":
    main()
