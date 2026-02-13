"""
SportsGameOdds SockJS Streaming Client
======================================
Real-time odds updates via SockJS (Pusher fallback transport).

Since WebSocket is disabled on the Pusher app, we use SockJS xhr_streaming.
"""

import json
import time
import random
import string
import threading
import requests
from typing import Callable, Optional

API_KEY = "7546525eada0352b926e60dbc6c42cb0"
BASE_URL = "https://api.sportsgameodds.com/v2"
SOCKJS_BASE = "https://sockjs-us2.pusher.com/pusher"


class SGOSockJSClient:
    """SportsGameOdds streaming client using SockJS transport."""

    def __init__(self, api_key: str, feed: str = "events:upcoming", league_id: str = "NBA",
                 on_update: Optional[Callable] = None):
        self.api_key = api_key
        self.feed = feed
        self.league_id = league_id
        self.on_update = on_update or self._default_on_update

        # Connection state
        self.connected = False
        self.subscribed = False
        self.socket_id = None
        self.running = False

        # Stream config
        self.pusher_key = None
        self.pusher_options = None
        self.channel = None
        self.events = {}

        # Stats
        self.updates_received = 0
        self.messages_received = 0

    def get_stream_config(self):
        """Get WebSocket connection details from API."""
        print(f"[INIT] Fetching stream config for {self.feed}...")

        params = {'feed': self.feed}
        if self.league_id:
            params['leagueID'] = self.league_id

        r = requests.get(
            f"{BASE_URL}/stream/events",
            headers={'x-api-key': self.api_key},
            params=params,
            timeout=30
        )

        if r.status_code != 200:
            raise Exception(f"Failed to get stream config: {r.status_code}")

        data = r.json()
        self.pusher_key = data['pusherKey']
        self.pusher_options = data['pusherOptions']
        self.channel = data['channel']

        for event in data.get('data', []):
            self.events[event['eventID']] = event

        print(f"[INIT] Channel: {self.channel}")
        print(f"[INIT] Initial events: {len(self.events)}")

    def _generate_session_id(self):
        """Generate SockJS session identifiers."""
        server_id = ''.join(random.choices(string.digits, k=3))
        session_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        return server_id, session_id

    def _send_message(self, server_id: str, session_id: str, data: dict):
        """Send a message via xhr_send."""
        url = f"{SOCKJS_BASE}/{server_id}/{session_id}/xhr_send?key={self.pusher_key}"
        payload = json.dumps([json.dumps(data)])

        r = requests.post(url, data=payload, timeout=10,
                         headers={'Content-Type': 'application/json'})
        return r.status_code == 204

    def _authenticate_channel(self, channel_name: str):
        """Authenticate for presence channel."""
        auth_endpoint = self.pusher_options.get('channelAuthorization', {}).get('endpoint')
        headers = self.pusher_options.get('channelAuthorization', {}).get('headers', {})
        headers['Content-Type'] = 'application/json'

        r = requests.post(auth_endpoint, headers=headers, json={
            'socket_id': self.socket_id,
            'channel_name': channel_name
        }, timeout=10)

        if r.status_code != 200:
            raise Exception(f"Auth failed: {r.status_code}")

        return r.json()

    def _parse_sockjs_message(self, line: str):
        """Parse a SockJS message frame."""
        if not line or line[0] == 'h':  # heartbeat
            return None

        if line[0] == 'o':  # open frame
            return {'type': 'open'}

        if line[0] == 'c':  # close frame
            return {'type': 'close', 'data': json.loads(line[1:])}

        if line[0] == 'a':  # array of messages
            messages = json.loads(line[1:])
            return {'type': 'messages', 'data': [json.loads(m) for m in messages]}

        return None

    def _handle_pusher_message(self, msg: dict, server_id: str, session_id: str):
        """Handle a Pusher protocol message."""
        event = msg.get('event', '')

        if event == 'pusher:connection_established':
            data = json.loads(msg.get('data', '{}'))
            self.socket_id = data.get('socket_id')
            self.connected = True
            print(f"[CONNECTED] Socket ID: {self.socket_id}")

            # Subscribe to channel
            self._subscribe_to_channel(server_id, session_id)

        elif event == 'pusher_internal:subscription_succeeded':
            self.subscribed = True
            print(f"[SUBSCRIBED] {msg.get('channel')}")

        elif event == 'data':
            self._handle_odds_update(msg)

        elif event == 'pusher:error':
            print(f"[ERROR] {msg.get('data')}")

    def _subscribe_to_channel(self, server_id: str, session_id: str):
        """Subscribe to the events channel."""
        print(f"[SUBSCRIBE] {self.channel}")

        auth_data = self._authenticate_channel(self.channel)

        subscribe_msg = {
            'event': 'pusher:subscribe',
            'data': {
                'channel': self.channel,
                'auth': auth_data.get('auth'),
                'channel_data': auth_data.get('channel_data')
            }
        }

        self._send_message(server_id, session_id, subscribe_msg)

    def _handle_odds_update(self, msg: dict):
        """Handle real-time odds update."""
        self.updates_received += 1

        try:
            changed_events = json.loads(msg.get('data', '[]'))
            event_ids = [e['eventID'] for e in changed_events]

            print(f"\n{'='*50}")
            print(f"[UPDATE #{self.updates_received}] {len(event_ids)} event(s) changed @ {time.strftime('%H:%M:%S')}")

            # Fetch full event data
            self._fetch_updated_events(event_ids)

            # Call user callback
            self.on_update(event_ids, self.events)

        except Exception as e:
            print(f"[ERROR] {e}")

    def _fetch_updated_events(self, event_ids: list):
        """Fetch full event data for changed events."""
        if not event_ids:
            return

        start = time.time()
        r = requests.get(
            f"{BASE_URL}/events",
            headers={'x-api-key': self.api_key},
            params={'eventIDs': ','.join(event_ids)},
            timeout=10
        )
        fetch_time = (time.time() - start) * 1000

        if r.status_code == 200:
            data = r.json()
            for event in data.get('data', []):
                self.events[event['eventID']] = event
            print(f"   Fetched {len(data.get('data', []))} events in {fetch_time:.0f}ms")

    def _default_on_update(self, event_ids: list, events: dict):
        """Default update handler - just print event IDs."""
        for eid in event_ids[:3]:
            print(f"   - {eid[:50]}...")

    def connect(self):
        """Connect and start streaming."""
        self.get_stream_config()

        server_id, session_id = self._generate_session_id()
        stream_url = f"{SOCKJS_BASE}/{server_id}/{session_id}/xhr_streaming?key={self.pusher_key}"

        print(f"\n[STREAM] Connecting via SockJS...")
        self.running = True

        while self.running:
            try:
                with requests.post(stream_url, stream=True, timeout=60) as r:
                    if r.status_code != 200:
                        print(f"[ERROR] HTTP {r.status_code}")
                        break

                    for line in r.iter_lines(decode_unicode=True):
                        if not self.running:
                            break

                        if not line:
                            continue

                        self.messages_received += 1
                        # Debug: show raw line (truncated)
                        if line[0] != 'h':  # Skip heartbeat spam
                            print(f"[RAW] {line[:100]}..." if len(line) > 100 else f"[RAW] {line}")
                        parsed = self._parse_sockjs_message(line)

                        if parsed is None:
                            continue

                        if parsed['type'] == 'open':
                            print("[SOCKJS] Connection opened, waiting for Pusher handshake...")

                        elif parsed['type'] == 'messages':
                            print(f"[DEBUG] Received {len(parsed['data'])} message(s)")
                            for msg in parsed['data']:
                                print(f"[DEBUG] Event: {msg.get('event', 'unknown')}")
                                self._handle_pusher_message(msg, server_id, session_id)

                        elif parsed['type'] == 'close':
                            print(f"[SOCKJS] Connection closed: {parsed['data']}")
                            break

            except requests.exceptions.Timeout:
                print("[TIMEOUT] Reconnecting...")
                continue
            except requests.exceptions.RequestException as e:
                print(f"[ERROR] {e}")
                if self.running:
                    time.sleep(2)
                    continue
                break

    def stop(self):
        """Stop streaming."""
        self.running = False


def main():
    """Test the SockJS streaming client."""
    print("=" * 60)
    print("SportsGameOdds SockJS Streaming Test")
    print("=" * 60)

    client = SGOSockJSClient(
        api_key=API_KEY,
        feed="events:upcoming",
        league_id="NBA"
    )

    try:
        client.connect()
    except KeyboardInterrupt:
        print("\n[STOP] Shutting down...")
        client.stop()

    print(f"\n[STATS] Updates received: {client.updates_received}")
    print(f"[STATS] Messages received: {client.messages_received}")


if __name__ == "__main__":
    main()
