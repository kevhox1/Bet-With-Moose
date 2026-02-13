"""
SportsGameOdds WebSocket Streaming Client
==========================================
Real-time odds updates via Pusher protocol.

Usage:
    python websocket_stream.py

This connects to the SportsGameOdds WebSocket and receives
real-time notifications when NBA event odds change.
"""

import json
import time
import threading
import requests
import websocket

API_KEY = "7546525eada0352b926e60dbc6c42cb0"
BASE_URL = "https://api.sportsgameodds.com/v2"


class SGOWebSocketClient:
    """SportsGameOdds WebSocket client using Pusher protocol."""

    def __init__(self, api_key: str, feed: str = "events:upcoming", league_id: str = "NBA"):
        self.api_key = api_key
        self.feed = feed
        self.league_id = league_id
        self.ws = None
        self.socket_id = None
        self.connected = False
        self.subscribed = False

        # Stream config (populated from /stream/events)
        self.pusher_key = None
        self.pusher_options = None
        self.channel = None
        self.events = {}  # eventID -> event data

        # Stats
        self.updates_received = 0
        self.last_update_time = None

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
            raise Exception(f"Failed to get stream config: {r.status_code} - {r.text}")

        data = r.json()
        self.pusher_key = data['pusherKey']
        self.pusher_options = data['pusherOptions']
        self.channel = data['channel']

        # Store initial events
        for event in data.get('data', []):
            self.events[event['eventID']] = event

        print(f"[INIT] Pusher Key: {self.pusher_key}")
        print(f"[INIT] Channel: {self.channel}")
        print(f"[INIT] Cluster: {self.pusher_options.get('cluster')}")
        print(f"[INIT] Initial events: {len(self.events)}")

        return data

    def build_ws_url(self):
        """Build WebSocket URL from Pusher options."""
        ws_host = self.pusher_options.get('wsHost', f"ws-{self.pusher_options.get('cluster', 'us2')}.pusher.com")
        # Don't include explicit port - wss defaults to 443
        return f"wss://{ws_host}/app/{self.pusher_key}?protocol=7&client=js&version=8.0.1&flash=false"

    def authenticate_channel(self, channel_name: str):
        """Authenticate for private/presence channel."""
        auth_endpoint = self.pusher_options.get('channelAuthorization', {}).get('endpoint')
        if not auth_endpoint:
            print("[AUTH] No auth endpoint - public channel")
            return None

        print(f"[AUTH] Authenticating for channel: {channel_name}")

        headers = self.pusher_options.get('channelAuthorization', {}).get('headers', {})
        headers['Content-Type'] = 'application/json'

        payload = {
            'socket_id': self.socket_id,
            'channel_name': channel_name
        }

        r = requests.post(auth_endpoint, headers=headers, json=payload, timeout=10)

        if r.status_code != 200:
            raise Exception(f"Auth failed: {r.status_code} - {r.text}")

        return r.json()

    def on_message(self, ws, message):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(message)
            event = data.get('event', '')

            if event == 'pusher:connection_established':
                conn_data = json.loads(data.get('data', '{}'))
                self.socket_id = conn_data.get('socket_id')
                self.connected = True
                print(f"[CONNECTED] Socket ID: {self.socket_id}")

                # Subscribe to channel after connection
                self.subscribe_to_channel()

            elif event == 'pusher_internal:subscription_succeeded':
                self.subscribed = True
                print(f"[SUBSCRIBED] Channel: {data.get('channel')}")

            elif event == 'pusher:error':
                err_data = json.loads(data.get('data', '{}'))
                print(f"[ERROR] {err_data.get('message', 'Unknown error')}")

            elif event == 'data':
                # This is our odds update event!
                self.handle_odds_update(data)

            elif event == 'pusher:pong':
                pass  # Heartbeat response

            else:
                print(f"[EVENT] {event}: {data.get('data', '')[:100]}...")

        except Exception as e:
            print(f"[ERROR] Processing message: {e}")

    def handle_odds_update(self, data):
        """Handle real-time odds update notification."""
        self.updates_received += 1
        self.last_update_time = time.time()

        try:
            changed_events = json.loads(data.get('data', '[]'))
            event_ids = [e['eventID'] for e in changed_events]

            print(f"\n[UPDATE #{self.updates_received}] {len(event_ids)} event(s) changed")
            for eid in event_ids[:3]:  # Show first 3
                print(f"   - {eid}")

            # Fetch full event data
            self.fetch_updated_events(event_ids)

        except Exception as e:
            print(f"[ERROR] Handling update: {e}")

    def fetch_updated_events(self, event_ids: list):
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
        else:
            print(f"   Fetch failed: {r.status_code}")

    def subscribe_to_channel(self):
        """Subscribe to the events channel."""
        print(f"[SUBSCRIBE] Subscribing to {self.channel}...")

        # Check if it's a presence/private channel
        if self.channel.startswith('presence-') or self.channel.startswith('private-'):
            auth_data = self.authenticate_channel(self.channel)
            subscribe_msg = {
                'event': 'pusher:subscribe',
                'data': {
                    'channel': self.channel,
                    'auth': auth_data.get('auth'),
                    'channel_data': auth_data.get('channel_data')
                }
            }
        else:
            subscribe_msg = {
                'event': 'pusher:subscribe',
                'data': {'channel': self.channel}
            }

        self.ws.send(json.dumps(subscribe_msg))

    def on_error(self, ws, error):
        """Handle WebSocket errors."""
        print(f"[WS ERROR] {error}")

    def on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close."""
        print(f"[WS CLOSED] Code: {close_status_code}, Msg: {close_msg}")
        self.connected = False
        self.subscribed = False

    def on_open(self, ws):
        """Handle WebSocket open."""
        print("[WS OPEN] Connection established, waiting for Pusher handshake...")

    def send_ping(self):
        """Send Pusher ping to keep connection alive."""
        if self.ws and self.connected:
            self.ws.send(json.dumps({'event': 'pusher:ping', 'data': {}}))

    def start_heartbeat(self):
        """Start heartbeat thread."""
        def heartbeat_loop():
            while self.connected:
                time.sleep(30)
                if self.connected:
                    self.send_ping()
                    print(f"[HEARTBEAT] Updates: {self.updates_received}, Events tracked: {len(self.events)}")

        thread = threading.Thread(target=heartbeat_loop, daemon=True)
        thread.start()

    def connect(self):
        """Connect to WebSocket and start streaming."""
        # Get stream config first
        self.get_stream_config()

        # Build WebSocket URL
        ws_url = self.build_ws_url()
        print(f"\n[CONNECT] {ws_url}")

        # Create WebSocket connection
        self.ws = websocket.WebSocketApp(
            ws_url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )

        # Start heartbeat
        self.start_heartbeat()

        # Run WebSocket (blocking)
        print("[STREAM] Starting WebSocket stream... (Ctrl+C to stop)\n")
        self.ws.run_forever()

    def disconnect(self):
        """Disconnect from WebSocket."""
        if self.ws:
            self.ws.close()


def main():
    """Test the WebSocket streaming client."""
    print("=" * 60)
    print("SportsGameOdds WebSocket Streaming Test")
    print("=" * 60)

    client = SGOWebSocketClient(
        api_key=API_KEY,
        feed="events:upcoming",
        league_id="NBA"
    )

    try:
        client.connect()
    except KeyboardInterrupt:
        print("\n[STOP] Shutting down...")
        client.disconnect()

    print(f"\n[STATS] Total updates received: {client.updates_received}")
    print(f"[STATS] Events tracked: {len(client.events)}")


if __name__ == "__main__":
    main()
