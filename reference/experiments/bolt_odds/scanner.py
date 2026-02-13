"""
Bolt Odds Scanner Adapter
=========================
Drop-in replacement for nba_value_scanner.py using Bolt Odds WebSocket API.

Provides the same interface as the TheOddsAPI scanner:
- scan_for_opportunities(state, verbose) -> (DataFrame, status_string)
- Uses real-time WebSocket streaming instead of REST polling
"""

import asyncio
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import pandas as pd
import numpy as np

# Add project src directory to path for imports
EXPERIMENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(EXPERIMENT_DIR))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'src'))

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    print("WARNING: websockets not installed. Run: pip install websockets")

# =============================================================================
# CONFIGURATION
# =============================================================================

BOLT_ODDS_API_KEY = "24ad4285-3c06-4a2a-bc86-77d67ab1cec0"
BOLT_ODDS_WS_URL = f"wss://spro.agency/api?key={BOLT_ODDS_API_KEY}"

# Map Bolt Odds sportsbook names to our abbreviations
BOLT_BOOK_MAPPING = {
    'draftkings': 'DK',
    'fanduel': 'FD',
    'betmgm': 'MG',
    'espnbet': 'ES',
    'thescore': 'TS',
    'pinnacle': 'PN',
    'ps3838': 'PN',  # PS3838 is Pinnacle's Asian arm
    'betrivers': 'BR',
    'hardrock': 'RK',
    'ballybet': 'BB',
    'pokerstars': 'PS',
    'bwin': 'BW',
    'bet99': 'B9',
    'playnow': 'PY',
    'bovada': 'BV',
    'bodog': 'BD',
    'betonline': 'BO',
    'sportsinteraction': 'SI',
    'miseojeu': 'MJ',
    'neobet': 'NB',
    '888': '88',
    'betfair': 'BF',
    'paddypower': 'PP',
    'partysports': 'PT',
    'leovegas': 'LV',
    'tonybet': 'TB',
    'dk predictions': 'DP',  # DraftKings predictions market
}

# Map Bolt Odds market names to TheOddsAPI format
BOLT_MARKET_MAPPING = {
    'Points': 'player_points_alternate',
    'Rebounds': 'player_rebounds_alternate',
    'Assists': 'player_assists_alternate',
    'Threes': 'player_threes_alternate',
    'Blocks': 'player_blocks_alternate',
    'Steals': 'player_steals_alternate',
    'Double-Doubles': 'player_double_double',
    'Triple-Doubles': 'player_triple_double',
    'First Basket': 'player_first_basket',
    'First Team Basket': 'player_first_team_basket',
    'First Field Goal': 'player_first_basket',  # Treat same as first basket
    # Combo props
    'Points + Rebounds': 'player_points_rebounds',
    'Points + Assists': 'player_points_assists',
    'Points + Assists + Rebounds': 'player_points_rebounds_assists',
    'Assists + Rebounds': 'player_rebounds_assists',
    'Steals + Blocks': 'player_blocks_steals',
}

# Markets we care about (longshots)
TARGET_MARKETS = {
    'player_double_double', 'player_triple_double',
    'player_first_basket', 'player_first_team_basket',
    'player_points_alternate', 'player_rebounds_alternate',
    'player_assists_alternate', 'player_blocks_alternate',
    'player_steals_alternate', 'player_threes_alternate',
}

# Book order for output
BOOK_ORDER = ['PN', 'DK', 'FD', 'MG', 'ES', 'TS', 'BR', 'RK', 'BB', 'PS', 'BW', 'BV', 'BO', 'SI']

# NBA Team Abbreviations
NBA_TEAM_ABBREV = {
    'Atlanta Hawks': 'ATL', 'Boston Celtics': 'BOS', 'Brooklyn Nets': 'BKN',
    'Charlotte Hornets': 'CHA', 'Chicago Bulls': 'CHI', 'Cleveland Cavaliers': 'CLE',
    'Dallas Mavericks': 'DAL', 'Denver Nuggets': 'DEN', 'Detroit Pistons': 'DET',
    'Golden State Warriors': 'GSW', 'Houston Rockets': 'HOU', 'Indiana Pacers': 'IND',
    'Los Angeles Clippers': 'LAC', 'Los Angeles Lakers': 'LAL', 'LA Clippers': 'LAC',
    'LA Lakers': 'LAL', 'Memphis Grizzlies': 'MEM', 'Miami Heat': 'MIA',
    'Milwaukee Bucks': 'MIL', 'Minnesota Timberwolves': 'MIN', 'New Orleans Pelicans': 'NOP',
    'New York Knicks': 'NYK', 'Oklahoma City Thunder': 'OKC', 'Orlando Magic': 'ORL',
    'Philadelphia 76ers': 'PHI', 'Phoenix Suns': 'PHX', 'Portland Trail Blazers': 'POR',
    'Sacramento Kings': 'SAC', 'San Antonio Spurs': 'SAS', 'Toronto Raptors': 'TOR',
    'Utah Jazz': 'UTA', 'Washington Wizards': 'WAS',
}

# State-specific legal sportsbooks (only alert on these for each state)
STATE_LEGAL_BOOKS = {
    'az': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'RK', 'BB', 'FL'],
    'co': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'BB', 'CI', 'FL'],
    'ct': ['DK', 'FD', 'FN', 'FL'],
    'dc': ['DK', 'FD', 'MG', 'CZ', 'FL'],
    'il': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'BB', 'FL'],
    'in': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'RK', 'CI', 'FL'],
    'ia': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'RK', 'BB', 'FL'],
    'ks': ['DK', 'FD', 'MG', 'CZ', 'ES', 'BR', 'RK', 'BB', 'CI', 'FL'],
    'ky': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'FL'],
    'la': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'FL'],
    'ma': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'FL'],
    'md': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'BB', 'BP', 'FL'],
    'mi': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'BB', 'RK', 'FL'],
    'mo': ['DK', 'FD', 'MG', 'CZ', 'FN', 'CI', 'FL'],
    'nc': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'BB', 'FL'],
    'nh': ['DK', 'FL'],
    'nj': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'RK', 'BP', 'FL'],
    'ny': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'FL'],
    'oh': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'RK', 'BB', 'FL'],
    'or': ['DK', 'FL'],
    'pa': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'BP', 'FL'],
    'tn': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'RK', 'FL'],
    'va': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'RK', 'BB', 'FL'],
    'vt': ['DK', 'FD', 'FN', 'FL'],
    'wv': ['DK', 'FD', 'MG', 'CZ', 'FN', 'BR', 'FL'],
    'wy': ['DK', 'FD', 'MG', 'CZ', 'FL'],
}

# Books to ALWAYS exclude from alerts (sharp books)
EXCLUDED_BOOKS = ['PN', 'BV', 'BO']

# Custom alert thresholds for Bolt Odds test bot
# FIRE: kelly >= 1.0, coverage >= 8
# VALUE (combined Outlier + Value Longshot): coverage >= 4, odds > +300, kelly >= 0.05
BOLT_ALERT_THRESHOLDS = {
    'FIRE': {'min_kelly': 1.0, 'min_coverage': 8},
    'VALUE': {'min_kelly': 0.05, 'min_coverage': 4, 'min_odds': 300},
}

# Import de-vig functions from main scanner
from nba_value_scanner import (
    american_to_probability, probability_to_american,
    calculate_fair_probability, calculate_ev_percentage,
    calculate_kelly, calculate_percent_vs_next,
    format_market_name, GLOBAL_WEIGHTS, MARKET_MULTIPLIERS,
    ALERT_THRESHOLDS,
)


# =============================================================================
# BOLT ODDS DATA STORE (Real-time state)
# =============================================================================

class BoltOddsStore:
    """
    Maintains real-time state of all NBA odds from Bolt Odds WebSocket.
    Thread-safe for use with asyncio.
    """

    def __init__(self):
        self.games: Dict[str, Dict] = {}  # game_id -> game info
        self.odds: Dict[str, Dict[str, Dict]] = defaultdict(lambda: defaultdict(dict))
        # odds[game_id][sportsbook] = {outcome_key: outcome_data}
        self.last_update = None
        self.connected = False
        self.update_count = 0
        self._lock = threading.Lock()

    def clear(self):
        with self._lock:
            self.games.clear()
            self.odds.clear()
            self.update_count = 0

    def process_message(self, data: dict):
        """Process incoming WebSocket message."""
        action = data.get('action', '')

        if action == 'initial_state':
            self._process_initial_state(data.get('data', {}))
        elif action == 'line_update':
            self._process_line_update(data.get('data', {}))
        elif action == 'game_update':
            self._process_game_update(data.get('data', {}))
        elif action == 'game_removed':
            self._process_game_removed(data.get('data', {}))
        elif action == 'sport_clear':
            self._process_sport_clear(data.get('data', {}))

        self.last_update = datetime.now(timezone.utc)
        self.update_count += 1

    def _process_initial_state(self, data: dict):
        """Process initial state message."""
        sport = data.get('sport', '')
        if sport != 'NBA':
            return

        # Prefer 'game' field (readable name) for consistent keys, fall back to universal_game_id
        info = data.get('info', {})
        game_id = data.get('game', '') or info.get('game', '') or data.get('universal_game_id', '')
        sportsbook = data.get('sportsbook', '').lower()

        if not game_id or not sportsbook:
            return

        with self._lock:
            # Store game info
            info = data.get('info', {})

            # Check explicit live flags first
            is_live = info.get('is_live', False) or info.get('live', False) or info.get('status', '') == 'live'

            # Also check by game start time - if game has started, treat as live
            if not is_live:
                when_str = info.get('when', '')
                if when_str:
                    try:
                        # Format: "2026-01-25, 08:00 PM"
                        game_time = datetime.strptime(when_str, '%Y-%m-%d, %I:%M %p')
                        # Assume times are ET, convert to UTC for comparison
                        game_time_utc = game_time.replace(tzinfo=timezone.utc) + timedelta(hours=5)
                        now_utc = datetime.now(timezone.utc)
                        # If game started more than 5 minutes ago, consider it live
                        if now_utc > game_time_utc + timedelta(minutes=5):
                            is_live = True
                    except (ValueError, TypeError):
                        pass  # Can't parse time, leave is_live as False

            if game_id not in self.games:
                self.games[game_id] = {
                    'game': data.get('game', ''),
                    'home_team': data.get('home_team', ''),
                    'away_team': data.get('away_team', ''),
                    'when': info.get('when', ''),
                    'is_live': is_live,
                }
            else:
                # Update live status if it changes
                self.games[game_id]['is_live'] = is_live

            # Store outcomes
            outcomes = data.get('outcomes', {})
            for outcome_key, outcome_data in outcomes.items():
                self.odds[game_id][sportsbook][outcome_key] = outcome_data

    def _process_line_update(self, data: dict):
        """Process line update message."""
        sport = data.get('sport', '')
        if sport != 'NBA':
            return

        # Use consistent game_id - prefer 'game' field
        info = data.get('info', {})
        game_id = data.get('game', '') or info.get('game', '') or data.get('universal_game_id', '')
        sportsbook = data.get('sportsbook', '').lower()
        outcomes = data.get('outcomes', {})

        if not game_id or not sportsbook:
            return

        with self._lock:
            for outcome_key, outcome_data in outcomes.items():
                self.odds[game_id][sportsbook][outcome_key] = outcome_data

    def _process_game_update(self, data: dict):
        """Process full game update."""
        self._process_initial_state(data)

    def _process_game_removed(self, data: dict):
        """Remove a game."""
        # Use consistent game_id - prefer 'game' field
        info = data.get('info', {})
        game_id = data.get('game', '') or info.get('game', '') or data.get('universal_game_id', '')
        sportsbook = data.get('sportsbook', '').lower()

        if not game_id:
            return

        with self._lock:
            if sportsbook and game_id in self.odds:
                self.odds[game_id].pop(sportsbook, None)
            elif game_id in self.games:
                self.games.pop(game_id, None)
                self.odds.pop(game_id, None)

    def _process_sport_clear(self, data: dict):
        """Clear all data for a sport."""
        sport = data.get('sport', '')
        if sport == 'NBA':
            self.clear()

    def get_snapshot(self) -> Tuple[Dict, Dict]:
        """Get thread-safe copy of current state."""
        with self._lock:
            games_copy = dict(self.games)
            odds_copy = {
                g: {b: dict(outcomes) for b, outcomes in books.items()}
                for g, books in self.odds.items()
            }
        return games_copy, odds_copy


# Global store instance
_store = BoltOddsStore()
_ws_task = None
_ws_loop = None


# =============================================================================
# WEBSOCKET CONNECTION MANAGEMENT
# =============================================================================

async def _websocket_listener():
    """Background WebSocket listener that maintains connection and updates store."""
    global _store

    reconnect_delay = 1

    while True:
        try:
            async with websockets.connect(
                BOLT_ODDS_WS_URL,
                max_size=50 * 1024 * 1024,  # 50MB max message
                ping_interval=30,
                ping_timeout=10,
            ) as ws:
                _store.connected = True
                reconnect_delay = 1  # Reset on successful connect

                # Wait for ack
                msg = await ws.recv()
                data = json.loads(msg)
                if data.get('action') != 'socket_connected':
                    continue

                # Subscribe to NBA
                await ws.send(json.dumps({"action": "subscribe", "sports": ["NBA"]}))

                # Listen for messages
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)

                    if data.get('action') == 'ping':
                        continue

                    _store.process_message(data)

        except Exception as e:
            _store.connected = False
            print(f"[BoltOdds] Connection error: {e}. Reconnecting in {reconnect_delay}s...")
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, 30)


def start_websocket_background():
    """Start WebSocket listener in background thread."""
    global _ws_task, _ws_loop

    if _ws_loop is not None:
        return  # Already running

    def run_loop():
        global _ws_loop
        _ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_ws_loop)
        _ws_loop.run_until_complete(_websocket_listener())

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()

    # Wait for initial connection
    for _ in range(50):  # 5 seconds max
        if _store.connected:
            break
        time.sleep(0.1)


def ensure_connected():
    """Ensure WebSocket is connected, start if needed."""
    if not WEBSOCKETS_AVAILABLE:
        raise RuntimeError("websockets library not installed")

    if not _store.connected:
        start_websocket_background()
        # Wait a bit for initial data
        time.sleep(2)


# =============================================================================
# DATA TRANSFORMATION
# =============================================================================

def transform_to_scanner_format(games: Dict, odds: Dict, state: str = 'ny') -> Dict:
    """
    Transform Bolt Odds data to match TheOddsAPI scanner format.

    Returns all_market_data dict in format:
    {
        "Player|market_key|line|side|game_id": {
            "market_key": "player_points_alternate",
            "DK": {"price": +150, "link": "...", "mobile_link": "..."},
            ...
        }
    }
    """
    all_market_data = {}

    for game_id, books in odds.items():
        # Skip live games - only use pre-game odds
        game_info = games.get(game_id, {})
        if game_info.get('is_live', False):
            continue

        for sportsbook, outcomes in books.items():
            # Map sportsbook name
            book_abbrev = BOLT_BOOK_MAPPING.get(sportsbook)
            if not book_abbrev:
                continue

            for outcome_key, outcome_data in outcomes.items():
                # Parse outcome
                market_name = outcome_data.get('outcome_name', '')
                market_key = BOLT_MARKET_MAPPING.get(market_name)

                if not market_key or market_key not in TARGET_MARKETS:
                    continue

                player = outcome_data.get('outcome_target', '')
                if not player:
                    continue

                # Parse odds
                odds_str = outcome_data.get('odds', '')
                if isinstance(odds_str, dict):
                    # Some have bid/ask
                    odds_str = odds_str.get('bid', odds_str.get('ask', ''))

                try:
                    price = int(odds_str.replace('+', ''))
                except (ValueError, AttributeError):
                    continue

                # Parse line and side
                line = outcome_data.get('outcome_line')
                over_under = outcome_data.get('outcome_over_under')

                if over_under == 'Over' or over_under == 'O':
                    side = 'Over'
                elif over_under == 'Under' or over_under == 'U':
                    side = 'Under'
                elif market_key in ('player_double_double', 'player_triple_double'):
                    # Yes/No markets
                    if 'yes' in outcome_key.lower() or price > 0:
                        side = 'Yes'
                    else:
                        side = 'No'
                elif market_key in ('player_first_basket', 'player_first_team_basket'):
                    side = 'Yes'  # First basket is always "Yes this player scores first"
                else:
                    continue

                line_str = str(line) if line else '0'

                # Create bet ID
                bet_id = f"{player}|{market_key}|{line_str}|{side}|{game_id}"

                if bet_id not in all_market_data:
                    all_market_data[bet_id] = {'market_key': market_key}

                # Get link and process for correct state
                link = outcome_data.get('link', '')
                mobile_link = link
                desktop_link = link

                # Convert Canadian FanDuel links to US domain first
                if 'sportsbook.fanduel.ca' in desktop_link:
                    desktop_link = desktop_link.replace('sportsbook.fanduel.ca', 'sportsbook.fanduel.com')
                    mobile_link = mobile_link.replace('sportsbook.fanduel.ca', 'sportsbook.fanduel.com')

                # Process FanDuel links - replace any state prefix with target state
                if 'sportsbook.fanduel.com' in desktop_link:
                    # Replace existing state prefix (e.g., ca., on., pa.) or add if missing
                    if re.search(r'https://[a-z]{2}\.sportsbook\.fanduel\.com', desktop_link):
                        desktop_link = re.sub(
                            r'https://[a-z]{2}\.sportsbook\.fanduel\.com',
                            f'https://{state}.sportsbook.fanduel.com',
                            desktop_link
                        )
                    elif 'https://sportsbook.fanduel.com' in desktop_link:
                        desktop_link = desktop_link.replace(
                            'https://sportsbook.fanduel.com',
                            f'https://{state}.sportsbook.fanduel.com'
                        )

                # Process BetRivers links - replace any state prefix with target state
                if 'betrivers.com' in desktop_link:
                    # Replace existing state prefix (e.g., on., pa., ny.)
                    if re.search(r'https://[a-z]{2}\.betrivers\.com', desktop_link):
                        desktop_link = re.sub(
                            r'https://[a-z]{2}\.betrivers\.com',
                            f'https://{state}.betrivers.com',
                            desktop_link
                        )
                    # Also update mobile link for BetRivers
                    if re.search(r'https://[a-z]{2}\.betrivers\.com', mobile_link):
                        mobile_link = re.sub(
                            r'https://[a-z]{2}\.betrivers\.com',
                            f'https://{state}.betrivers.com',
                            mobile_link
                        )

                # Process BetMGM links - replace any state prefix with target state
                # BetMGM uses format: sports.{state}.betmgm.com
                if 'betmgm.com' in desktop_link:
                    if re.search(r'https://sports\.[a-z]{2}\.betmgm\.com', desktop_link):
                        desktop_link = re.sub(
                            r'https://sports\.[a-z]{2}\.betmgm\.com',
                            f'https://sports.{state}.betmgm.com',
                            desktop_link
                        )
                    elif 'https://sports.betmgm.com' in desktop_link:
                        desktop_link = desktop_link.replace(
                            'https://sports.betmgm.com',
                            f'https://sports.{state}.betmgm.com'
                        )
                    # Also update mobile link for BetMGM
                    if re.search(r'https://sports\.[a-z]{2}\.betmgm\.com', mobile_link):
                        mobile_link = re.sub(
                            r'https://sports\.[a-z]{2}\.betmgm\.com',
                            f'https://sports.{state}.betmgm.com',
                            mobile_link
                        )
                    elif 'https://sports.betmgm.com' in mobile_link:
                        mobile_link = mobile_link.replace(
                            'https://sports.betmgm.com',
                            f'https://sports.{state}.betmgm.com'
                        )

                # Process BallyBet links - replace any state prefix with target state
                # BallyBet uses format: {state}.ballybet.com
                if 'ballybet.com' in desktop_link:
                    if re.search(r'https://[a-z]{2}\.ballybet\.com', desktop_link):
                        desktop_link = re.sub(
                            r'https://[a-z]{2}\.ballybet\.com',
                            f'https://{state}.ballybet.com',
                            desktop_link
                        )
                    elif 'https://www.ballybet.com' in desktop_link:
                        desktop_link = desktop_link.replace(
                            'https://www.ballybet.com',
                            f'https://{state}.ballybet.com'
                        )
                    elif 'https://ballybet.com' in desktop_link:
                        desktop_link = desktop_link.replace(
                            'https://ballybet.com',
                            f'https://{state}.ballybet.com'
                        )
                    # Also update mobile link for BallyBet
                    if re.search(r'https://[a-z]{2}\.ballybet\.com', mobile_link):
                        mobile_link = re.sub(
                            r'https://[a-z]{2}\.ballybet\.com',
                            f'https://{state}.ballybet.com',
                            mobile_link
                        )
                    elif 'https://www.ballybet.com' in mobile_link:
                        mobile_link = mobile_link.replace(
                            'https://www.ballybet.com',
                            f'https://{state}.ballybet.com'
                        )
                    elif 'https://ballybet.com' in mobile_link:
                        mobile_link = mobile_link.replace(
                            'https://ballybet.com',
                            f'https://{state}.ballybet.com'
                        )

                all_market_data[bet_id][book_abbrev] = {
                    'price': price,
                    'link': desktop_link,
                    'mobile_link': mobile_link,
                }

    return all_market_data


# =============================================================================
# MAIN SCANNER FUNCTION (Same interface as nba_value_scanner.py)
# =============================================================================

def scan_for_opportunities(state: str = 'ny', verbose: bool = True) -> Tuple[pd.DataFrame, Optional[str]]:
    """
    Main scanning function - compatible with nba_value_scanner.py interface.

    Uses real-time Bolt Odds WebSocket data instead of TheOddsAPI polling.

    Returns:
        Tuple of (DataFrame with all opportunities, status string)
    """
    ensure_connected()

    if verbose:
        print(f"🔄 Using Bolt Odds real-time data (last update: {_store.last_update})")
        print(f"   Updates received: {_store.update_count}")

    # Get current snapshot
    games, odds = _store.get_snapshot()

    if not games:
        if verbose:
            print("❌ No NBA games in Bolt Odds feed.")
        return pd.DataFrame(), "No games"

    if verbose:
        print(f"✅ Found {len(games)} NBA games with odds from {sum(len(b) for b in odds.values())} sportsbook feeds")

    # Transform to scanner format
    all_market_data = transform_to_scanner_format(games, odds, state)

    if verbose:
        print(f"📊 Parsed {len(all_market_data)} unique betting opportunities")

    if not all_market_data:
        return pd.DataFrame(), f"Connected, {_store.update_count} updates"

    # Build opposite side lookup (for de-vigging)
    if verbose:
        print("   Building two-way market lookup...")

    opposite_lookup = {}
    for bet_id, data in all_market_data.items():
        parts = bet_id.split('|')
        if len(parts) != 5:
            continue

        player, market_key, line, side, game_id = parts

        if side == 'Over':
            opp_side = 'Under'
        elif side == 'Under':
            opp_side = 'Over'
        elif side == 'Yes':
            opp_side = 'No'
        elif side == 'No':
            opp_side = 'Yes'
        else:
            continue

        opp_bet_id = f"{player}|{market_key}|{line}|{opp_side}|{game_id}"
        if opp_bet_id in all_market_data:
            opp_book_odds = {k: v for k, v in all_market_data[opp_bet_id].items() if k != 'market_key'}
            opposite_lookup[bet_id] = opp_book_odds

    if verbose:
        print(f"   Found {len(opposite_lookup)} two-way pairs")

    # Analyze opportunities (using same logic as nba_value_scanner)
    opportunities = []

    for bet_id, data in all_market_data.items():
        parts = bet_id.split('|')
        if len(parts) != 5:
            continue

        player, market_key, line_str, side, game_id = parts
        line = float(line_str) if line_str and line_str != '0' else None

        # Get book data (must include 'price' key for calculate_fair_probability)
        book_data = {k: v for k, v in data.items() if k != 'market_key' and isinstance(v, dict) and 'price' in v}

        if not book_data:
            continue

        # Get opposite side data
        opp_data = {}
        if bet_id in opposite_lookup:
            opp_data = {k: v for k, v in opposite_lookup[bet_id].items() if isinstance(v, dict) and 'price' in v}

        # Calculate fair probability
        fair_prob, method = calculate_fair_probability(
            book_data, opp_data, market_key
        )
        coverage = len(book_data)  # Number of books with this line

        if fair_prob is None or fair_prob <= 0 or fair_prob >= 1:
            continue

        fair_american = probability_to_american(fair_prob)

        # Find best price and EV
        book_prices = {k: v['price'] for k, v in book_data.items()}
        best_book = max(book_prices, key=book_prices.get)
        best_price = book_prices[best_book]
        best_decimal = (best_price / 100 + 1) if best_price > 0 else (100 / abs(best_price) + 1)

        ev = calculate_ev_percentage(fair_prob, best_decimal)
        kelly = calculate_kelly(ev / 100, best_decimal)

        if ev <= 0:
            continue

        # Get link
        best_link = data.get(best_book, {}).get('link', '')
        raw_link = data.get(best_book, {}).get('link', '')

        # Get game info
        game_info = games.get(game_id, {})

        # Format game with team abbreviations and EST time
        home_team = game_info.get('home_team', '')
        away_team = game_info.get('away_team', '')
        when_str = game_info.get('when', '')
        game_formatted = format_game_info(home_team, away_team, when_str)

        # Process links - state-specific with FanDuel desktop/mobile logic
        desktop_link = ''
        mobile_link = ''
        if raw_link:
            # Replace state placeholder if present
            mobile_link = raw_link.replace('{state}', state).replace('{STATE}', state.upper())
            desktop_link = mobile_link

            # FanDuel special handling: add state prefix for desktop
            # e.g., sportsbook.fanduel.com -> ny.sportsbook.fanduel.com
            if 'sportsbook.fanduel.com' in desktop_link and f'{state}.' not in desktop_link:
                desktop_link = desktop_link.replace(
                    'https://sportsbook.fanduel.com',
                    f'https://{state}.sportsbook.fanduel.com'
                )

        # Calculate percent vs next best
        sorted_prices = sorted(book_prices.items(), key=lambda x: x[1], reverse=True)
        pct_vs_next, is_outlier = calculate_percent_vs_next(sorted_prices)

        opportunities.append({
            'player': player,
            'market': format_market_name(market_key),
            'market_key': market_key,
            'line': line,
            'side': side,
            'game': game_info.get('game', game_id),
            'game_formatted': game_formatted,
            'home_team': home_team,
            'away_team': away_team,
            'fair_prob': fair_prob,
            'fair_american': fair_american,
            'best_book': best_book,
            'best_price': best_price,
            'ev': ev,
            'kelly': kelly,
            'coverage': coverage,
            'method': method,
            'pct_vs_next': pct_vs_next,
            'is_outlier': is_outlier,
            'link': raw_link,
            'desktop_link': desktop_link,
            'mobile_link': mobile_link,
            'bet_id': bet_id,
        })

    if not opportunities:
        return pd.DataFrame(), f"Connected, {_store.update_count} updates, no +EV"

    df = pd.DataFrame(opportunities)

    # Sort by Kelly (best opportunities first)
    df = df.sort_values('kelly', ascending=False)

    status = f"Bolt Odds real-time | {_store.update_count} updates | {len(games)} games"

    if verbose:
        print(f"✅ Found {len(df)} +EV opportunities")

    return df, status


# =============================================================================
# ALERT FUNCTIONS (Same as nba_value_scanner.py)
# =============================================================================

def get_alerts(df: pd.DataFrame, state: str = 'ny') -> pd.DataFrame:
    """
    Filter DataFrame to only alertable opportunities.

    Uses BOLT_ALERT_THRESHOLDS:
    - FIRE: kelly >= 1.0, coverage >= 8
    - VALUE: kelly >= 0.05, coverage >= 4, odds > +300

    Also filters to only books legal in the specified state.
    """
    if df.empty:
        return df

    legal_books = STATE_LEGAL_BOOKS.get(state.lower(), STATE_LEGAL_BOOKS['ny'])

    alerts = []
    for _, row in df.iterrows():
        # Skip books not legal in state or excluded books
        if row['best_book'] not in legal_books:
            continue
        if row['best_book'] in EXCLUDED_BOOKS:
            continue

        for tier, thresholds in BOLT_ALERT_THRESHOLDS.items():
            if row['kelly'] < thresholds['min_kelly']:
                continue
            if row['coverage'] < thresholds['min_coverage']:
                continue
            if 'min_odds' in thresholds and row['best_price'] < thresholds['min_odds']:
                continue

            row_copy = row.copy()
            row_copy['tier'] = tier
            alerts.append(row_copy)
            break

    return pd.DataFrame(alerts)


def format_alert_message(row: pd.Series, scan_time: datetime = None) -> str:
    """
    Format a single alert for Telegram (HTML format).

    Format:
    ⚡ VALUE
    Norman Powell Over 7.5 Rebounds
    📍 PHX @ MIA, 2026-01-25, 7:00PM EST
    💰 Best: RK +850 | Fair: +596
    📈 EV: 36.6% | Kelly: 1.08 | Cov: 3
    🔗 Desktop · Mobile

    ⚡ Bolt Odds | Scanned: 7:15:32 PM EST
    """
    tier = row.get('tier', 'VALUE')
    tier_emoji = {'FIRE': '🔥', 'VALUE': '🎯'}.get(tier, '📊')

    line_str = f" {row['line']}" if row['line'] else ""

    # Format game with team abbreviations and EST time
    game_formatted = row.get('game_formatted', row['game'])

    msg = f"{tier_emoji} <b>{tier}</b>\n"
    msg += f"<b>{row['player']}</b> {row['side']}{line_str} {row['market']}\n"
    msg += f"📍 {game_formatted}\n"
    msg += f"💰 Best: <b>{row['best_book']} {row['best_price']:+d}</b> | Fair: {row['fair_american']:+d}\n"
    msg += f"📈 EV: <b>{row['ev']:.1f}%</b> | Kelly: {row['kelly']:.2f} | Cov: {row['coverage']}\n"

    # Links (desktop + mobile for FanDuel)
    if row.get('desktop_link') and row.get('mobile_link') and row.get('desktop_link') != row.get('mobile_link'):
        msg += f"\n🔗 <a href=\"{row['desktop_link']}\">Desktop</a> · <a href=\"{row['mobile_link']}\">Mobile</a>"
    elif row.get('link'):
        msg += f"\n🔗 <a href=\"{row['link']}\">Place Bet</a>"

    # Scan timestamp
    if scan_time is None:
        scan_time = datetime.now(timezone.utc)
    est_time = scan_time - timedelta(hours=5)
    scan_str = est_time.strftime('%I:%M:%S %p EST').lstrip('0')

    msg += f"\n\n⚡ <i>Bolt Odds | Scanned: {scan_str}</i>"

    return msg


def format_game_info(home_team: str, away_team: str, when_str: str) -> str:
    """
    Format game info as 'AWA @ HOM, 2026-01-25, 7:00PM EST'
    """
    # Get team abbreviations
    home_abbrev = NBA_TEAM_ABBREV.get(home_team, home_team[:3].upper())
    away_abbrev = NBA_TEAM_ABBREV.get(away_team, away_team[:3].upper())

    # Parse and format time
    # Input format from Bolt: "2026-01-25, 08" or "2026-01-25, 07:00 PM"
    try:
        if ',' in when_str:
            parts = when_str.split(', ')
            date_part = parts[0]
            time_part = parts[1] if len(parts) > 1 else ''

            # Try to parse time
            if time_part:
                # Handle "08" format (hour only)
                if len(time_part) <= 2 and time_part.isdigit():
                    hour = int(time_part)
                    if hour < 12:
                        time_str = f"{hour}:00PM EST" if hour == 0 else f"{hour}:00PM EST"
                    else:
                        time_str = f"{hour-12 if hour > 12 else hour}:00PM EST"
                else:
                    # Already formatted
                    time_str = time_part + " EST" if "EST" not in time_part else time_part
            else:
                time_str = ""

            return f"{away_abbrev} @ {home_abbrev}, {date_part}, {time_str}"
        else:
            return f"{away_abbrev} @ {home_abbrev}, {when_str}"
    except Exception:
        return f"{away_abbrev} @ {home_abbrev}, {when_str}"


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    print("Testing Bolt Odds Scanner...")
    print("=" * 60)

    df, status = scan_for_opportunities(state='pa', verbose=True)

    print(f"\nStatus: {status}")
    print(f"Opportunities found: {len(df)}")

    if not df.empty:
        print("\nTop 5 opportunities:")
        print(df[['player', 'market', 'side', 'best_book', 'best_price', 'ev', 'kelly']].head())

        alerts = get_alerts(df)
        print(f"\nAlerts: {len(alerts)}")

        if not alerts.empty:
            print("\nSample alert:")
            print(format_alert_message(alerts.iloc[0]))
