"""
SportsGameOdds API Provider
===========================
REST and WebSocket client for SportsGameOdds.com API.
Designed as a drop-in replacement for TheOddsAPI data fetching.

Toggle between REST polling and WebSocket streaming via config.
"""

import os
import json
import time
import asyncio
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
import requests
from dotenv import load_dotenv

# WebSocket support (optional - gracefully handle if not installed)
try:
    import websockets
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False

try:
    import pusher
    PUSHER_AVAILABLE = True
except ImportError:
    PUSHER_AVAILABLE = False

load_dotenv()

# =============================================================================
# CONFIGURATION
# =============================================================================

# API Base URLs
REST_BASE_URL = "https://api.sportsgameodds.com/v2"
STREAMING_BASE_URL = "wss://ws.sportsgameodds.com"  # Placeholder - confirm actual URL

# Default settings
DEFAULT_TIMEOUT = 30
DEFAULT_POLL_INTERVAL = 60  # seconds between REST polls

# =============================================================================
# SPORTSBOOK MAPPING
# =============================================================================
# Maps SportsGameOdds bookmaker IDs to our internal abbreviations
# NOTE: These mappings need to be verified against actual API response format

SPORTSGAMEODDS_BOOK_MAPPING = {
    # Major US Books (verified from API responses)
    'draftkings': 'DK',
    'fanduel': 'FD',
    'betmgm': 'MG',
    'caesars': 'CZ',
    'espnbet': 'ES',
    'fanatics': 'FN',
    'betrivers': 'BR',
    'sugarhouse': 'BR',  # Same as BetRivers
    'hardrockbet': 'RK',
    'ballybet': 'BB',
    'betparx': 'BP',
    'circa': 'CI',

    # Sharp/International Books
    'pinnacle': 'PN',
    'bet365': 'B3',
    'matchbook': 'MB',
    'bookmakereu': 'BK',

    # Offshore Books
    'bovada': 'BV',
    'betonline': 'BO',
    'betus': 'BU',
    'mybookie': 'MY',
    'gtbets': 'GT',
    'everygame': 'EG',
    'betanysports': 'BA',
    'lowvig': 'LV',
    'coolbet': 'CB',

    # DFS/Social
    'fliff': 'FL',
    'prizepicks': 'PP',
    'underdog': 'UD',

    # Exchanges
    'prophetexchange': 'PX',
    'sporttrade': 'ST',
    'novig': 'NV',
    'kalshi': 'KA',

    # International (from API)
    'sportsbet': 'SB',
    'pointsbet': 'PB',
    'tab': 'TA',
    'tabtouch': 'TT',
    'betvictor': 'BT',
    'tipico': 'TI',
    'coral': 'CO',
    'ladbrokes': 'LB',
    'betsson': 'BS',
    'nordicbet': 'NB',
    '888sport': '88',
    '1xbet': '1X',
    'playup': 'PU',
    'casumo': 'CA',
    'grosvenor': 'GR',
    'leovegas': 'LE',
    'livescorebet': 'LS',
    'virginbet': 'VB',
    'thescorebet': 'TS',

    # Skip unknown
    'unknown': None,
}

# Reverse mapping for lookups
ABBREV_TO_SPORTSGAMEODDS = {v: k for k, v in SPORTSGAMEODDS_BOOK_MAPPING.items()}

# =============================================================================
# MARKET MAPPING
# =============================================================================
# Maps our market keys to SportsGameOdds market identifiers
# NOTE: These need to be verified against actual API response format

# Market stat IDs from SportsGameOdds API
# Format: statID-playerID-periodID-betTypeID-sideID
# e.g., points-LEBRON_JAMES_1_NBA-game-ou-over
SPORTSGAMEODDS_STAT_MAPPING = {
    # statID -> our market name
    'points': 'player_points_alternate',
    'rebounds': 'player_rebounds_alternate',
    'assists': 'player_assists_alternate',
    'threePointersMade': 'player_threes_alternate',
    'blocks': 'player_blocks_alternate',
    'steals': 'player_steals_alternate',
    'doubleDouble': 'player_double_double',
    'tripleDouble': 'player_triple_double',
    'firstBasketScorer': 'player_first_basket',
    'firstTeamScorer': 'player_first_team_basket',
    # Combo props
    'points+rebounds': 'player_points_rebounds',
    'points+assists': 'player_points_assists',
    'points+rebounds+assists': 'player_points_rebounds_assists',
    'rebounds+assists': 'player_rebounds_assists',
    'steals+blocks': 'player_blocks_steals',
}

# Reverse mapping
MARKET_TO_SPORTSGAMEODDS_STAT = {v: k for k, v in SPORTSGAMEODDS_STAT_MAPPING.items()}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class OddsOutcome:
    """Single odds outcome from a sportsbook."""
    book_key: str
    book_abbrev: str
    price: int  # American odds
    player: str
    market_key: str
    side: str  # Over/Under or Yes/No
    line: float
    link: str = ""


@dataclass
class EventData:
    """NBA game event data."""
    event_id: str
    home_team: str
    away_team: str
    commence_time: datetime
    status: str = "scheduled"

    @property
    def game(self) -> str:
        return f"{self.away_team} @ {self.home_team}"


@dataclass
class MarketSnapshot:
    """Snapshot of all odds for a specific market/player/line combination."""
    bet_id: str
    event: EventData
    player: str
    market_key: str
    side: str
    line: float
    outcomes: Dict[str, OddsOutcome] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add_outcome(self, outcome: OddsOutcome):
        """Add or update an outcome from a sportsbook."""
        self.outcomes[outcome.book_abbrev] = outcome


# =============================================================================
# REST API CLIENT
# =============================================================================

class SportsGameOddsRESTClient:
    """
    REST API client for SportsGameOdds.
    Polls /events endpoint for NBA odds data.
    """

    def __init__(self, api_key: str, poll_interval: int = DEFAULT_POLL_INTERVAL):
        self.api_key = api_key
        self.poll_interval = poll_interval
        self.base_url = REST_BASE_URL
        self.session = requests.Session()
        # Use x-api-key header for authentication (verified working)
        self.session.headers.update({
            'x-api-key': api_key,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        })
        self._last_request_time = 0
        self._requests_remaining = None

    def _make_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Make a REST API request with rate limiting."""
        url = f"{self.base_url}{endpoint}"

        try:
            response = self.session.get(url, params=params, timeout=DEFAULT_TIMEOUT)

            # Track rate limit headers if present
            self._requests_remaining = response.headers.get('X-RateLimit-Remaining')

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                print(f"[SportsGameOdds] Authentication failed - check API key")
                return None
            elif response.status_code == 429:
                print(f"[SportsGameOdds] Rate limited - waiting before retry")
                time.sleep(60)  # Wait 1 minute on rate limit
                return None
            else:
                print(f"[SportsGameOdds] API error {response.status_code}: {response.text}")
                return None

        except requests.exceptions.Timeout:
            print(f"[SportsGameOdds] Request timeout for {endpoint}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"[SportsGameOdds] Request error: {e}")
            return None

    def get_nba_events(self, include_ended: bool = False) -> List[Dict]:
        """
        Fetch NBA events with odds.

        Args:
            include_ended: If False, only return upcoming/live games

        Returns list of event dictionaries with structure:
        {
            'eventID': str,
            'teams': {'home': {...}, 'away': {...}},
            'status': {'startsAt': str, 'ended': bool, ...},
            'odds': {'oddID': {'byBookmaker': {...}, ...}},
            'players': {'playerID': {'name': str, ...}}
        }
        """
        params = {
            'leagueID': 'NBA',
        }
        if not include_ended:
            params['ended'] = 'false'

        result = self._make_request('/events', params)

        if result and 'data' in result:
            events = result['data']
            # Filter to only events with odds
            return [e for e in events if e.get('odds')]
        elif result and isinstance(result, list):
            return [e for e in result if e.get('odds')]

        return []

    def get_event_odds(self, event_id: str, markets: List[str] = None) -> Optional[Dict]:
        """
        Fetch odds for a specific event.

        Args:
            event_id: The event/game ID
            markets: List of market types to fetch (optional)
        """
        params = {}
        if markets:
            params['markets'] = ','.join(markets)

        return self._make_request(f'/events/{event_id}', params)

    def get_player_props(self, event_id: str) -> Optional[Dict]:
        """
        Fetch player prop odds for an event.
        """
        return self._make_request(f'/events/{event_id}/props')

    def get_account_usage(self) -> Optional[Dict]:
        """Get API usage statistics."""
        return self._make_request('/account/usage')

    @property
    def requests_remaining(self) -> Optional[str]:
        return self._requests_remaining


# =============================================================================
# WEBSOCKET STREAMING CLIENT
# =============================================================================

class SportsGameOddsWebSocketClient:
    """
    WebSocket streaming client for SportsGameOdds.
    Maintains persistent connection for real-time odds updates.

    NOTE: WebSocket endpoint details need to be confirmed with actual API docs.
    This is a skeleton implementation.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._ws = None
        self._running = False
        self._callbacks: List[Callable[[Dict], None]] = []
        self._thread = None
        self._event_loop = None
        self._subscriptions = set()

        if not WEBSOCKET_AVAILABLE:
            print("[SportsGameOdds] Warning: websockets library not installed")
            print("  Install with: pip install websockets")

    def subscribe(self, event_ids: List[str] = None, leagues: List[str] = None):
        """
        Subscribe to odds updates for specific events or leagues.

        Args:
            event_ids: List of event IDs to subscribe to
            leagues: List of league IDs (e.g., ['NBA'])
        """
        if leagues:
            for league in leagues:
                self._subscriptions.add(f"league:{league}")
        if event_ids:
            for event_id in event_ids:
                self._subscriptions.add(f"event:{event_id}")

    def on_update(self, callback: Callable[[Dict], None]):
        """Register a callback for odds updates."""
        self._callbacks.append(callback)

    async def _connect_and_listen(self):
        """Internal async method to maintain WebSocket connection."""
        if not WEBSOCKET_AVAILABLE:
            return

        uri = f"{STREAMING_BASE_URL}?apiKey={self.api_key}"

        while self._running:
            try:
                async with websockets.connect(uri) as websocket:
                    self._ws = websocket
                    print("[SportsGameOdds] WebSocket connected")

                    # Send subscription message
                    sub_message = {
                        'action': 'subscribe',
                        'channels': list(self._subscriptions)
                    }
                    await websocket.send(json.dumps(sub_message))

                    # Listen for messages
                    async for message in websocket:
                        try:
                            data = json.loads(message)
                            self._handle_message(data)
                        except json.JSONDecodeError:
                            print(f"[SportsGameOdds] Invalid JSON: {message[:100]}")

            except Exception as e:
                print(f"[SportsGameOdds] WebSocket error: {e}")
                if self._running:
                    print("[SportsGameOdds] Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)

    def _handle_message(self, data: Dict):
        """Process incoming WebSocket message and notify callbacks."""
        # Handle different message types based on API format
        msg_type = data.get('type', data.get('event', 'unknown'))

        if msg_type in ('odds_update', 'update', 'data'):
            for callback in self._callbacks:
                try:
                    callback(data)
                except Exception as e:
                    print(f"[SportsGameOdds] Callback error: {e}")
        elif msg_type == 'heartbeat':
            pass  # Ignore heartbeats
        elif msg_type == 'error':
            print(f"[SportsGameOdds] Server error: {data.get('message', data)}")

    def start(self):
        """Start the WebSocket connection in a background thread."""
        if self._running:
            return

        self._running = True

        def run_loop():
            self._event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._event_loop)
            self._event_loop.run_until_complete(self._connect_and_listen())

        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()
        print("[SportsGameOdds] WebSocket client started")

    def stop(self):
        """Stop the WebSocket connection."""
        self._running = False
        if self._event_loop:
            self._event_loop.call_soon_threadsafe(self._event_loop.stop)
        if self._thread:
            self._thread.join(timeout=5)
        print("[SportsGameOdds] WebSocket client stopped")


# =============================================================================
# UNIFIED PROVIDER INTERFACE
# =============================================================================

class SportsGameOddsProvider:
    """
    Unified provider that can use either REST or WebSocket based on config.

    Usage:
        provider = SportsGameOddsProvider(api_key, mode='rest')
        events = provider.fetch_nba_odds()
    """

    def __init__(self, api_key: str = None, mode: str = 'rest'):
        """
        Initialize the provider.

        Args:
            api_key: SportsGameOdds API key (or reads from SPORTSGAMEODDS_API_KEY env var)
            mode: 'rest' for polling or 'websocket' for streaming
        """
        self.api_key = api_key or os.getenv('SPORTSGAMEODDS_API_KEY')
        self.mode = mode.lower()

        if not self.api_key:
            raise ValueError("SportsGameOdds API key required. Set SPORTSGAMEODDS_API_KEY env var or pass api_key parameter.")

        # Initialize the appropriate client
        self.rest_client = SportsGameOddsRESTClient(self.api_key)
        self.ws_client = None

        if self.mode == 'websocket':
            self.ws_client = SportsGameOddsWebSocketClient(self.api_key)

        # Cache for WebSocket mode
        self._events_cache: Dict[str, EventData] = {}
        self._odds_cache: Dict[str, MarketSnapshot] = {}
        self._cache_lock = threading.Lock()

    def start_streaming(self, on_update: Callable[[Dict], None] = None):
        """
        Start WebSocket streaming (only in websocket mode).

        Args:
            on_update: Optional callback for each odds update
        """
        if self.mode != 'websocket':
            print("[SportsGameOdds] Streaming only available in websocket mode")
            return

        if self.ws_client:
            self.ws_client.subscribe(leagues=['NBA'])
            if on_update:
                self.ws_client.on_update(on_update)
            # Also register internal cache updater
            self.ws_client.on_update(self._update_cache_from_ws)
            self.ws_client.start()

    def stop_streaming(self):
        """Stop WebSocket streaming."""
        if self.ws_client:
            self.ws_client.stop()

    def _update_cache_from_ws(self, data: Dict):
        """Update internal cache from WebSocket message."""
        with self._cache_lock:
            # Parse incoming data and update caches
            # Format depends on actual API response structure
            event_id = data.get('eventID', data.get('event_id'))
            if event_id:
                # Update odds cache based on message structure
                pass  # TODO: Implement based on actual API format

    def fetch_nba_odds(self, markets: List[str] = None) -> Dict[str, MarketSnapshot]:
        """
        Fetch all NBA odds data.

        In REST mode: Makes API calls to fetch current odds
        In WebSocket mode: Returns cached data from stream

        Args:
            markets: List of market types to fetch (uses defaults if not specified)

        Returns:
            Dictionary of bet_id -> MarketSnapshot
        """
        if self.mode == 'websocket':
            with self._cache_lock:
                return dict(self._odds_cache)
        else:
            return self._fetch_odds_rest(markets)

    def _fetch_odds_rest(self, markets: List[str] = None) -> Dict[str, MarketSnapshot]:
        """Fetch odds using REST API."""
        result: Dict[str, MarketSnapshot] = {}

        # Default markets if not specified
        if not markets:
            markets = list(MARKET_MAPPING.keys())

        # Fetch events
        events_data = self.rest_client.get_nba_events()

        if not events_data:
            print("[SportsGameOdds] No NBA events found")
            return result

        print(f"[SportsGameOdds] Found {len(events_data)} NBA events")

        current_time = datetime.now(timezone.utc)

        for event_raw in events_data:
            # Parse event data (adjust field names based on actual API response)
            event = self._parse_event(event_raw)

            if not event:
                continue

            # Skip games that have started
            if event.commence_time <= current_time:
                continue

            # Parse odds from event data
            odds_data = event_raw.get('odds', event_raw.get('markets', {}))

            for market_key, market_data in self._iterate_markets(odds_data, markets):
                for outcome in self._parse_outcomes(market_data, event, market_key):
                    bet_id = f"{outcome.player}|{market_key}|{outcome.line}|{outcome.side}|{event.event_id}"

                    if bet_id not in result:
                        result[bet_id] = MarketSnapshot(
                            bet_id=bet_id,
                            event=event,
                            player=outcome.player,
                            market_key=market_key,
                            side=outcome.side,
                            line=outcome.line,
                        )

                    result[bet_id].add_outcome(outcome)

        print(f"[SportsGameOdds] Parsed {len(result)} unique betting opportunities")
        return result

    def _parse_event(self, raw: Dict) -> Optional[EventData]:
        """Parse raw API response into EventData."""
        try:
            # Adjust field names based on actual API response
            event_id = raw.get('eventID', raw.get('id', raw.get('event_id')))
            home_team = raw.get('homeTeam', raw.get('home_team', raw.get('home', {}).get('name', '')))
            away_team = raw.get('awayTeam', raw.get('away_team', raw.get('away', {}).get('name', '')))

            # Parse commence time
            commence_str = raw.get('startTime', raw.get('commence_time', raw.get('scheduled')))
            if isinstance(commence_str, str):
                # Handle various date formats
                for fmt in ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%d %H:%M:%S']:
                    try:
                        commence_time = datetime.strptime(commence_str, fmt).replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        continue
                else:
                    return None
            elif isinstance(commence_str, (int, float)):
                commence_time = datetime.fromtimestamp(commence_str, tz=timezone.utc)
            else:
                return None

            return EventData(
                event_id=event_id,
                home_team=home_team,
                away_team=away_team,
                commence_time=commence_time,
                status=raw.get('status', 'scheduled')
            )
        except Exception as e:
            print(f"[SportsGameOdds] Error parsing event: {e}")
            return None

    def _iterate_markets(self, odds_data: Dict, target_markets: List[str]):
        """Iterate through markets in the odds data."""
        # This needs to be adjusted based on actual API structure
        # Could be: odds_data['player_props']['points'] or odds_data['markets'][...]

        if isinstance(odds_data, dict):
            for market_key in odds_data:
                # Map SportsGameOdds market key to our format
                our_key = SPORTSGAMEODDS_TO_MARKET.get(market_key, market_key)
                if our_key in target_markets or market_key in target_markets:
                    yield our_key, odds_data[market_key]
        elif isinstance(odds_data, list):
            for market in odds_data:
                market_key = market.get('marketType', market.get('type', market.get('key', '')))
                our_key = SPORTSGAMEODDS_TO_MARKET.get(market_key, market_key)
                if our_key in target_markets or market_key in target_markets:
                    yield our_key, market

    def _parse_outcomes(self, market_data: Any, event: EventData, market_key: str) -> List[OddsOutcome]:
        """Parse outcomes from market data."""
        outcomes = []

        # Handle various response formats
        if isinstance(market_data, dict):
            # Could be organized by player or by bookmaker
            bookmakers = market_data.get('bookmakers', market_data.get('sportsbooks', []))

            if isinstance(bookmakers, list):
                for book in bookmakers:
                    book_key = book.get('key', book.get('id', book.get('name', ''))).lower()
                    book_abbrev = SPORTSGAMEODDS_BOOK_MAPPING.get(book_key)

                    if not book_abbrev:
                        continue

                    for outcome in book.get('outcomes', book.get('selections', [])):
                        parsed = self._parse_single_outcome(outcome, book_key, book_abbrev, market_key)
                        if parsed:
                            outcomes.append(parsed)

        elif isinstance(market_data, list):
            # Direct list of outcomes
            for item in market_data:
                book_key = item.get('sportsbook', item.get('book', '')).lower()
                book_abbrev = SPORTSGAMEODDS_BOOK_MAPPING.get(book_key)

                if not book_abbrev:
                    continue

                parsed = self._parse_single_outcome(item, book_key, book_abbrev, market_key)
                if parsed:
                    outcomes.append(parsed)

        return outcomes

    def _parse_single_outcome(self, data: Dict, book_key: str, book_abbrev: str, market_key: str) -> Optional[OddsOutcome]:
        """Parse a single outcome/selection."""
        try:
            player = data.get('player', data.get('description', data.get('participant', 'Unknown')))

            # Parse odds (handle both American and decimal)
            price = data.get('price', data.get('odds', data.get('americanOdds')))
            if isinstance(price, float) and price > 0 and price < 100:
                # Likely decimal odds, convert to American
                if price >= 2.0:
                    price = int((price - 1) * 100)
                else:
                    price = int(-100 / (price - 1))
            else:
                price = int(price) if price else 0

            side = data.get('name', data.get('side', data.get('type', 'Over')))
            # Normalize side names
            if side.lower() in ('over', 'o', 'yes', 'y'):
                side = 'Over' if side.lower() in ('over', 'o') else 'Yes'
            elif side.lower() in ('under', 'u', 'no', 'n'):
                side = 'Under' if side.lower() in ('under', 'u') else 'No'

            line = float(data.get('line', data.get('point', data.get('handicap', 0))) or 0)
            link = data.get('link', data.get('betLink', data.get('deeplink', '')))

            return OddsOutcome(
                book_key=book_key,
                book_abbrev=book_abbrev,
                price=price,
                player=player,
                market_key=market_key,
                side=side,
                line=line,
                link=link
            )
        except Exception as e:
            print(f"[SportsGameOdds] Error parsing outcome: {e}")
            return None

    @property
    def requests_remaining(self) -> Optional[str]:
        """Get remaining API requests (REST mode only)."""
        return self.rest_client.requests_remaining


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_provider(mode: str = None) -> SportsGameOddsProvider:
    """
    Factory function to create a SportsGameOdds provider.

    Reads configuration from environment variables:
    - SPORTSGAMEODDS_API_KEY: API key
    - SPORTSGAMEODDS_MODE: 'rest' or 'websocket' (default: rest)
    """
    api_key = os.getenv('SPORTSGAMEODDS_API_KEY')
    if not api_key:
        raise ValueError("SPORTSGAMEODDS_API_KEY environment variable not set")

    mode = mode or os.getenv('SPORTSGAMEODDS_MODE', 'rest')
    return SportsGameOddsProvider(api_key=api_key, mode=mode)


# =============================================================================
# TESTING / STANDALONE
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("SportsGameOdds Provider Test")
    print("=" * 60)

    api_key = os.getenv('SPORTSGAMEODDS_API_KEY')

    if not api_key:
        print("\nNo API key found. Set SPORTSGAMEODDS_API_KEY environment variable.")
        print("\nTo test, create a .env.test file with:")
        print("  SPORTSGAMEODDS_API_KEY=your_api_key_here")
        exit(1)

    print(f"\nAPI Key: {api_key[:8]}...{api_key[-4:]}")

    # Test REST client
    print("\n--- Testing REST Client ---")
    provider = SportsGameOddsProvider(api_key=api_key, mode='rest')

    print("\nFetching NBA events...")
    snapshots = provider.fetch_nba_odds()

    print(f"\nFound {len(snapshots)} betting opportunities")

    if snapshots:
        # Show sample
        sample_id = list(snapshots.keys())[0]
        sample = snapshots[sample_id]
        print(f"\nSample: {sample.player} - {sample.market_key}")
        print(f"  Event: {sample.event.game}")
        print(f"  Books: {list(sample.outcomes.keys())}")
