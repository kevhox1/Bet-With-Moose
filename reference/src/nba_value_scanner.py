"""
NBA Value Scanner for Telegram Bot
===================================
Emulates MKB_Scanner.ipynb de-vig methodology exactly.
"""

import requests
import pandas as pd
import numpy as np
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Optional

# Import odds caching (optional - gracefully handle if not available)
try:
    import odds_cache
    CACHING_ENABLED = True
except ImportError:
    CACHING_ENABLED = False

# =============================================================================
# CONFIGURATION
# =============================================================================

API_KEY = '6ea51cb342237ea2ebd4ac2c7015ab2e'
SPORT = 'basketball_nba'
REGIONS = 'us,us2,eu,us_ex'  # eu=Pinnacle, us_ex=exchanges (Kalshi, Novig, ProphetX)
ODDS_FORMAT = 'american'

# Standard player prop markets (commented out to reduce API calls)
# MARKETS_STANDARD = (
#     "player_points,player_rebounds,player_assists,player_threes,player_blocks,player_steals,"
#     "player_blocks_steals,player_points_rebounds_assists,"
#     "player_points_rebounds,player_points_assists,player_rebounds_assists"
# )

# Longshot-focused markets only (double/triple doubles, first basket, alternates)
MARKETS = (
    "player_double_double,player_triple_double,player_first_basket,player_first_team_basket,"
    "player_points_alternate,player_rebounds_alternate,player_assists_alternate,"
    "player_blocks_alternate,player_steals_alternate,player_threes_alternate"
)

# Book mapping from API keys to abbreviations
BOOK_MAPPING = {
    'pinnacle': 'PN',
    'circasports': 'CI',
    'fanduel': 'FD',
    'draftkings': 'DK',
    'betmgm': 'MG',
    'fanatics': 'FN',
    'williamhill_us': 'CZ',
    'espnbet': 'ES',
    'ballybet': 'BB',
    'betrivers': 'BR',
    'hardrockbet': 'RK',
    'betonlineag': 'BO',
    'rebet': 'RB',
    'bovada': 'BV',
    'fliff': 'FL',
    'betparx': 'BP',
    # US Betting Exchanges
    'kalshi': 'KA',
    'novig': 'NV',
    'prophetx': 'PX',
    'betopenly': 'BY',
}

# Book column order for output (exchanges at end)
BOOK_ORDER = ['PN', 'CI', 'FD', 'DK', 'MG', 'FN', 'CZ', 'ES', 'BB', 'RK', 'BR', 'RB', 'BV', 'BO', 'FL', 'BP', 'KA', 'NV', 'PX', 'BY']

# Global weights (V10 Pinnacle-Optimized)
# Note: Exchanges (KA, NV, PX, BY) are NOT included in fair value calculation
# because they represent market prices, not sharp book lines. They are used
# only as betting destinations when they offer +EV vs the calculated fair value.
GLOBAL_WEIGHTS = {
    'DK': 0.2027,
    'FD': 0.1599,
    'MG': 0.1580,
    'PN': 0.1328,
    'ES': 0.0883,
    'RK': 0.0828,
    'CZ': 0.0742,
    'BO': 0.0412,
    'BV': 0.0170,
    'BB': 0.0096,
    'BR': 0.0096,
    'FL': 0.0096,
    'FN': 0.0096,
    'RB': 0.0048,
    'BP': 0.0048,
    'CI': 0.0000,
    # Exchanges - zero weight for fair value calculation (used only as bet destinations)
    'KA': 0.0000,
    'NV': 0.0000,
    'PX': 0.0000,
    'BY': 0.0000,
}

# Supported states for multi-state links
SUPPORTED_STATES = ['ny', 'pa', 'nj']

# Books that require state-specific URLs
# FD = FanDuel (desktop only needs state prefix, mobile doesn't)
# BR = BetRivers, MG = BetMGM, BB = BallyBet (both desktop and mobile need state)
STATE_DEPENDENT_BOOKS = {
    'FD': {
        'desktop_pattern': 'https://{state}.sportsbook.fanduel.com',
        'mobile_pattern': 'https://sportsbook.fanduel.com',
        'detect': 'sportsbook.fanduel.com',
        'separate_mobile': True,  # FanDuel needs separate desktop/mobile rows
    },
    'BR': {
        'pattern': 'https://{state}.betrivers.com',
        'detect': 'betrivers.com',
        'separate_mobile': False,
    },
    'MG': {
        'pattern': 'https://sports.{state}.betmgm.com',
        'detect': 'betmgm.com',
        'separate_mobile': False,
    },
    'BB': {
        'pattern': 'https://{state}.ballybet.com',
        'detect': 'ballybet.com',
        'separate_mobile': False,
    },
}

# Default one-way multipliers by odds range (reverse-engineered from MKB data)
ONE_WAY_MULTIPLIERS = [
    0.88,  # < -200 (heavy favorite)
    0.90,  # -200 to -110
    0.92,  # -110 to +110
    0.89,  # +110 to +200
    0.86,  # +200 to +400
    0.84,  # +400 to +700
    0.82,  # +700 to +1000
    0.74,  # +1000 to +2000
    0.72,  # +2000 to +5000
    0.72,  # > +5000 (extreme longshot)
]

# Market-specific multipliers (reverse-engineered from MKB data)
# Used for short/medium odds where market type matters more than odds level
MARKET_MULTIPLIERS = {
    'player_double_double': 0.79,   # MKB avg: 0.788
    'player_triple_double': 0.70,   # MKB avg: 0.697
    'player_first_basket': 0.81,
    'player_first_team_basket': 0.82,
    'player_threes': 0.76,          # MKB avg for longshots: 0.763
    'player_rebounds': 0.79,        # MKB avg for longshots: 0.794
    'player_points': 0.76,          # MKB avg for longshots: 0.759
    'player_assists': 0.79,         # MKB avg for longshots: 0.787
    'player_steals': 0.85,          # MKB avg: 0.847
    'player_blocks': 0.87,          # MKB avg: 0.869
    'player_blocks_steals': 0.88,
    'player_points_rebounds_assists': 0.88,
    'player_rebounds_assists': 0.88,
    'player_points_rebounds': 0.88,
    'player_points_assists': 0.88,
}

# Longshot-specific multipliers for 1-way markets at +1000-2999
# These override the default odds-based multipliers for specific markets
LONGSHOT_MARKET_MULTIPLIERS = {
    'player_points': 0.76,          # MKB avg: 0.759
    'player_points_alternate': 0.76,
    'player_threes': 0.76,          # MKB avg: 0.763
    'player_threes_alternate': 0.76,
    'player_assists': 0.79,         # MKB avg: 0.787
    'player_assists_alternate': 0.79,
    'player_rebounds': 0.79,        # MKB avg: 0.794
    'player_rebounds_alternate': 0.79,
    'player_steals': 0.85,          # MKB avg: 0.847
    'player_steals_alternate': 0.85,
    'player_blocks': 0.87,          # MKB avg: 0.869
    'player_blocks_alternate': 0.87,
    'player_double_double': 0.79,   # MKB avg: 0.788
    'player_triple_double': 0.70,   # MKB avg: 0.697
}

# Extreme longshot multipliers for +3000 and higher
# MKB uses even more aggressive de-vigging at these odds levels
EXTREME_LONGSHOT_MULTIPLIERS = {
    'player_points': 0.70,          # MKB avg at +3000+: ~0.70
    'player_points_alternate': 0.70,
    'player_threes': 0.70,          # MKB avg at +3000+: ~0.70
    'player_threes_alternate': 0.70,
    'player_assists': 0.72,
    'player_assists_alternate': 0.72,
    'player_rebounds': 0.74,        # MKB avg at +3000+: ~0.74
    'player_rebounds_alternate': 0.74,
    'player_steals': 0.80,
    'player_steals_alternate': 0.80,
    'player_blocks': 0.82,
    'player_blocks_alternate': 0.82,
    'player_double_double': 0.74,
    'player_triple_double': 0.65,
}

# Markets forced to one-way calculation
FORCE_ONE_WAY_MARKETS = [
    'player_first_basket',
    'player_first_team_basket',
    'player_double_double',
    'player_triple_double',
]

# Confidence multipliers by coverage
CONFIDENCE_MULTIPLIERS = {
    1: 0.25, 2: 0.35, 3: 0.47, 4: 0.47, 5: 0.53,
    6: 0.56, 7: 0.62, 8: 0.70, 9: 0.72, 10: 0.81,
    11: 0.81, 12: 0.91, 13: 0.96, 14: 1.00, 15: 1.00,
}

# Alert tier thresholds (order matters: FIRE -> VALUE_LONGSHOT -> OUTLIER)
ALERT_THRESHOLDS = {
    'FIRE': {'min_kelly': 0.30, 'min_coverage': 8},
    'VALUE_LONGSHOT': {'min_kelly': 0.15, 'min_coverage': 5, 'min_odds': 500},
    'OUTLIER': {'min_kelly': 0.05, 'min_coverage': 3, 'min_pct_vs_next': 35},
}

# State for bet links
STATE = 'pa'

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def american_to_probability(odds: float) -> float:
    """Convert American odds to implied probability."""
    if pd.isna(odds) or odds == 0:
        return 0.0
    odds = float(odds)
    if odds > 0:
        return 100 / (odds + 100)
    else:
        return abs(odds) / (abs(odds) + 100)


def probability_to_american(prob: float) -> int:
    """Convert probability to American odds."""
    if prob <= 0 or prob >= 1:
        return 0
    if prob > 0.5:
        return int(round(-100 * prob / (1 - prob)))
    else:
        return int(round(100 * (1 - prob) / prob))


def get_one_way_multiplier(avg_odds: float) -> float:
    """Get the vig-removal multiplier based on average odds level."""
    if avg_odds < -200:
        return ONE_WAY_MULTIPLIERS[0]
    elif avg_odds < -110:
        return ONE_WAY_MULTIPLIERS[1]
    elif avg_odds <= 110:
        return ONE_WAY_MULTIPLIERS[2]
    elif avg_odds <= 200:
        return ONE_WAY_MULTIPLIERS[3]
    elif avg_odds <= 400:
        return ONE_WAY_MULTIPLIERS[4]
    elif avg_odds <= 700:
        return ONE_WAY_MULTIPLIERS[5]
    elif avg_odds <= 1000:
        return ONE_WAY_MULTIPLIERS[6]
    elif avg_odds <= 2000:
        return ONE_WAY_MULTIPLIERS[7]
    elif avg_odds <= 5000:
        return ONE_WAY_MULTIPLIERS[8]
    else:
        return ONE_WAY_MULTIPLIERS[9]


def get_confidence_multiplier(coverage: int) -> float:
    """Get confidence multiplier based on book coverage."""
    if coverage >= 15:
        return 1.0
    return CONFIDENCE_MULTIPLIERS.get(coverage, 0.50)


def calculate_fair_probability(
    book_odds: Dict[str, Dict],
    opposite_odds: Optional[Dict[str, Dict]] = None,
    market_key: str = '',
) -> Tuple[float, str]:
    """
    Calculate fair probability using MKB V10 methodology.

    HYBRID APPROACH (per-book basis):
        For EACH book:
        - If book has both sides available → use two-way proportional de-vig
        - If book only has one side → use one-way with multiplier
        Then combine all book fair probabilities using weighted average.

    Returns:
        Tuple of (fair_probability, calc_type)
        calc_type: 'hybrid' if mix of methods, '2-way' if all two-way, '1-way' if all one-way
    """
    if not book_odds:
        return 0.5, 'none'

    weighted_sum = 0
    weight_total = 0
    two_way_count = 0
    one_way_count = 0

    # Process each book individually
    for book_abbrev, data in book_odds.items():
        odds = data['price']
        implied_prob = american_to_probability(odds)

        if implied_prob <= 0:
            continue

        weight = GLOBAL_WEIGHTS.get(book_abbrev, 0.01)

        # Check if this specific book has the opposite side
        has_opposite = opposite_odds and book_abbrev in opposite_odds

        if has_opposite:
            # TWO-WAY: This book has both sides - use proportional de-vig
            opp_prob = american_to_probability(opposite_odds[book_abbrev]['price'])

            if opp_prob > 0:
                # Proportional de-vig: fair_prob = my_prob / (my_prob + opp_prob)
                fair_prob = implied_prob / (implied_prob + opp_prob)
                weighted_sum += fair_prob * weight
                weight_total += weight
                two_way_count += 1
                continue

        # ONE-WAY: This book only has one side - apply multiplier
        # Get the appropriate multiplier based on odds level
        odds_multiplier = get_one_way_multiplier(odds)

        # For extreme longshots (+3000 or higher), use most aggressive multipliers
        if odds >= 3000:
            extreme_multiplier = None
            for market_pattern, mult in EXTREME_LONGSHOT_MULTIPLIERS.items():
                if market_pattern in market_key:
                    extreme_multiplier = mult
                    break

            if extreme_multiplier is not None:
                multiplier = extreme_multiplier
            else:
                multiplier = odds_multiplier
        # For longshots (+1000 to +2999), use longshot multipliers
        elif odds >= 1000:
            longshot_multiplier = None
            for market_pattern, mult in LONGSHOT_MARKET_MULTIPLIERS.items():
                if market_pattern in market_key:
                    longshot_multiplier = mult
                    break

            if longshot_multiplier is not None:
                multiplier = longshot_multiplier
            else:
                multiplier = odds_multiplier
        else:
            # For non-longshots, check for market-specific multiplier
            market_multiplier = None
            for market_pattern, mult in MARKET_MULTIPLIERS.items():
                if market_pattern in market_key:
                    market_multiplier = mult
                    break

            # Use the HIGHER (more conservative) multiplier for non-longshots
            if market_multiplier is not None:
                multiplier = max(market_multiplier, odds_multiplier)
            else:
                multiplier = odds_multiplier

        fair_prob = implied_prob * multiplier
        weighted_sum += fair_prob * weight
        weight_total += weight
        one_way_count += 1

    if weight_total > 0:
        final_fair_prob = weighted_sum / weight_total

        # Determine calc type for reporting
        if two_way_count > 0 and one_way_count > 0:
            calc_type = 'hybrid'
        elif two_way_count > 0:
            calc_type = '2-way'
        else:
            calc_type = '1-way'

        return final_fair_prob, calc_type

    return 0.5, 'none'


def calculate_ev_percentage(fair_prob: float, decimal_odds: float) -> float:
    """Calculate Expected Value percentage."""
    if decimal_odds <= 1:
        return 0.0
    win_profit = decimal_odds - 1
    ev = (fair_prob * win_profit) - (1 - fair_prob)
    return ev * 100


def calculate_kelly(edge: float, decimal_odds: float, fraction: float = 0.25) -> float:
    """Calculate Kelly stake (Quarter Kelly by default)."""
    if decimal_odds <= 1 or edge <= 0:
        return 0.0
    kelly_full = edge / (decimal_odds - 1)
    kelly_fractional = kelly_full * fraction
    return kelly_fractional * 100


def calculate_percent_vs_next(sorted_prices: List[Tuple[str, float]]) -> Tuple[float, bool]:
    """
    Calculate how much better the best book is vs the next best.
    Returns (pct_vs_next, is_outlier).
    """
    if len(sorted_prices) < 2:
        return 0.0, False

    best_odds = sorted_prices[0][1]
    next_odds = sorted_prices[1][1]

    # Check if both odds are positive (use raw % difference)
    if best_odds > 0 and next_odds > 0:
        pct_vs_next = ((best_odds - next_odds) / next_odds) * 100
        is_outlier = pct_vs_next >= 35
    else:
        # Mixed signs - use implied probability difference
        best_prob = american_to_probability(best_odds)
        next_prob = american_to_probability(next_odds)
        prob_diff = next_prob - best_prob
        pct_vs_next = prob_diff * 100
        is_outlier = prob_diff >= 0.10

    return pct_vs_next, is_outlier


def format_market_name(market_key: str) -> str:
    """Convert API market key to display name."""
    name = market_key.replace('player_', '').replace('_', ' ').title()
    name = name.replace('Rebounds Assists', 'Rebounds + Assists')
    name = name.replace('Points Rebounds Assists', 'Points + Rebounds + Assists')
    name = name.replace('Points Rebounds', 'Points + Rebounds')
    name = name.replace('Points Assists', 'Points + Assists')
    name = name.replace('Blocks Steals', 'Blocks + Steals')
    name = name.replace(' Alternate', '')
    name = name.replace(' Q1', '')
    return name


def format_game_time(commence_time: datetime) -> Tuple[str, str]:
    """Format game time for display in ET."""
    et_time = commence_time - timedelta(hours=5)
    game_date = et_time.strftime('%Y-%m-%d')
    game_time = et_time.strftime('%I:%M %p').lstrip('0') + ' ET'
    return game_date, game_time


def get_book_url(book: str, state: str = 'pa') -> str:
    """Generate a generic sportsbook URL."""
    urls = {
        'DK': 'https://sportsbook.draftkings.com',
        'FD': 'https://sportsbook.fanduel.com',
        'MG': 'https://sports.betmgm.com',
        'CZ': 'https://sportsbook.caesars.com',
        'BR': 'https://www.betrivers.com',
        'FN': 'https://sportsbook.fanatics.com',
        'ES': 'https://espnbet.com',
        'RK': 'https://www.hardrocksportsbook.com',
        'BP': 'https://www.betparx.com',
        'PN': 'https://www.pinnacle.com',
        'BO': 'https://www.betonline.ag',
        'BV': 'https://www.bovada.lv',
        'FL': 'https://www.getfliff.com',
        'BB': 'https://www.ballybet.com',
        # US Betting Exchanges
        'KA': 'https://kalshi.com',
        'NV': 'https://www.novig.us',
        'PX': 'https://www.prophetx.co',
        'BY': 'https://app.betopenly.com',
    }
    return urls.get(book, '')


import re

def generate_multi_state_links(link: str, book_abbrev: str) -> dict:
    """
    Generate links for all supported states from a base link.

    Returns dict with structure:
    {
        'book': book_abbrev,
        'is_state_dependent': bool,
        'separate_mobile': bool,  # True only for FanDuel
        'desktop': {'ny': url, 'pa': url, 'nj': url} or single url string,
        'mobile': {'ny': url, 'pa': url, 'nj': url} or single url string,
    }
    """
    if not link:
        return {
            'book': book_abbrev,
            'is_state_dependent': False,
            'separate_mobile': False,
            'desktop': '',
            'mobile': '',
        }

    # Check if this book is state-dependent
    book_config = STATE_DEPENDENT_BOOKS.get(book_abbrev)

    if not book_config:
        # Not a state-dependent book (DK, PN, etc.) - return same link for all
        return {
            'book': book_abbrev,
            'is_state_dependent': False,
            'separate_mobile': False,
            'desktop': link,
            'mobile': link,
        }

    # Check if link matches this book's pattern
    if book_config['detect'] not in link:
        # Link doesn't match expected pattern, return as-is
        return {
            'book': book_abbrev,
            'is_state_dependent': False,
            'separate_mobile': False,
            'desktop': link,
            'mobile': link,
        }

    # Generate multi-state links
    is_fanduel = book_abbrev == 'FD'

    if is_fanduel:
        # FanDuel: desktop needs state prefix, mobile doesn't
        desktop_links = {}
        mobile_links = {}

        # Extract the path after the domain
        # Handle both with and without existing state prefix
        path_match = re.search(r'sportsbook\.fanduel\.com(/.*)?$', link)
        path = path_match.group(1) if path_match and path_match.group(1) else ''

        for state in SUPPORTED_STATES:
            desktop_links[state] = f"https://{state}.sportsbook.fanduel.com{path}"
            mobile_links[state] = f"https://sportsbook.fanduel.com{path}"

        return {
            'book': book_abbrev,
            'is_state_dependent': True,
            'separate_mobile': True,
            'desktop': desktop_links,
            'mobile': mobile_links,
        }
    else:
        # BetRivers, BetMGM, BallyBet: same URL format for desktop and mobile
        state_links = {}

        if book_abbrev == 'BR':
            # BetRivers: {state}.betrivers.com
            path_match = re.search(r'betrivers\.com(/.*)?$', link)
            path = path_match.group(1) if path_match and path_match.group(1) else ''
            for state in SUPPORTED_STATES:
                state_links[state] = f"https://{state}.betrivers.com{path}"

        elif book_abbrev == 'MG':
            # BetMGM: sports.{state}.betmgm.com
            path_match = re.search(r'betmgm\.com(/.*)?$', link)
            path = path_match.group(1) if path_match and path_match.group(1) else ''
            for state in SUPPORTED_STATES:
                state_links[state] = f"https://sports.{state}.betmgm.com{path}"

        elif book_abbrev == 'BB':
            # BallyBet: {state}.ballybet.com
            path_match = re.search(r'ballybet\.com(/.*)?$', link)
            path = path_match.group(1) if path_match and path_match.group(1) else ''
            for state in SUPPORTED_STATES:
                state_links[state] = f"https://{state}.ballybet.com{path}"

        return {
            'book': book_abbrev,
            'is_state_dependent': True,
            'separate_mobile': False,
            'desktop': state_links,
            'mobile': state_links,  # Same as desktop for non-FanDuel
        }


# =============================================================================
# MAIN SCANNER
# =============================================================================

def scan_for_opportunities(state: str = 'pa', verbose: bool = True, enable_caching: bool = False) -> Tuple[pd.DataFrame, Optional[str]]:
    """
    Main scanning function - emulates MKB_Scanner.ipynb exactly.

    Returns:
        Tuple of (DataFrame with all opportunities, requests_remaining string)
    """
    global STATE
    STATE = state.lower()

    # Start timing and caching session
    scan_start_time = time.time()
    scan_id = None
    if CACHING_ENABLED and enable_caching:
        try:
            odds_cache.init_cache_database()
            scan_id = odds_cache.start_scan_session(state=STATE)
        except Exception as e:
            if verbose:
                print(f"⚠️ Cache init error: {e}")
            scan_id = None

    if verbose:
        print(f"🔄 Connecting to TheOddsApi (Regions: {REGIONS})...")

    # Fetch events
    try:
        events_url = f'https://api.the-odds-api.com/v4/sports/{SPORT}/events?apiKey={API_KEY}'
        response = requests.get(events_url, timeout=30)
        if response.status_code != 200:
            if verbose:
                print(f"❌ API Error: {response.text}")
            return pd.DataFrame(), None
        events = response.json()
    except Exception as e:
        if verbose:
            print(f"❌ Connection Error: {e}")
        return pd.DataFrame(), None

    if not events:
        if verbose:
            print("❌ No scheduled games found.")
        return pd.DataFrame(), None

    if verbose:
        print(f"✅ Found {len(events)} scheduled games. Scanning for odds...")

    current_time = datetime.now(timezone.utc)
    all_market_data = {}
    event_info = {}
    requests_remaining = None

    # Harvest all odds data
    for event in events:
        commence_str = event['commence_time']
        commence_time = datetime.strptime(commence_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

        # Skip games that have already started
        if commence_time <= current_time:
            continue

        event_id = event['id']
        event_info[event_id] = {
            'home_team': event.get('home_team', ''),
            'away_team': event.get('away_team', ''),
            'commence_time': commence_time,
            'game': f"{event.get('away_team', '')} @ {event.get('home_team', '')}"
        }

        # Fetch odds for this event
        odds_url = f'https://api.the-odds-api.com/v4/sports/{SPORT}/events/{event_id}/odds'
        params = {
            'apiKey': API_KEY,
            'regions': REGIONS,
            'markets': MARKETS,
            'oddsFormat': 'american',
            'includeLinks': 'true',
            'linkState': STATE.upper(),
            'includeBetLimits': 'true',  # Shows only seeded/liquid markets on exchanges
        }

        try:
            odds_response = requests.get(odds_url, params=params, timeout=30)
            if odds_response.status_code != 200:
                continue
            odds_data = odds_response.json()
            requests_remaining = odds_response.headers.get('x-requests-remaining', 'N/A')
        except:
            continue

        # Parse bookmaker data
        for bookmaker in odds_data.get('bookmakers', []):
            book_key = bookmaker['key']

            if book_key not in BOOK_MAPPING:
                continue
            book_abbrev = BOOK_MAPPING[book_key]

            for market in bookmaker['markets']:
                market_key = market['key']

                for outcome in market['outcomes']:
                    player = outcome.get('description', 'Unknown')
                    side = outcome['name']
                    line = outcome.get('point', 0)
                    price = outcome['price']
                    link = outcome.get('link', bookmaker.get('link', ''))

                    # Process links - generate multi-state links for supported states (NY, PA, NJ)
                    # Replace any {state} placeholders first
                    if link:
                        link = link.replace('{state}', STATE).replace('{STATE}', STATE)

                    # Generate multi-state link data
                    link_data = generate_multi_state_links(link, book_abbrev)

                    # Create unique bet ID (matches MKB format)
                    bet_id = f"{player}|{market_key}|{line}|{side}|{event_id}"

                    if bet_id not in all_market_data:
                        all_market_data[bet_id] = {'market_key': market_key}

                    all_market_data[bet_id][book_abbrev] = {
                        'price': price,
                        'link_data': link_data,  # Multi-state link info
                        'link': link,  # Raw link string as fallback
                    }

    if verbose:
        print(f"📊 Parsed {len(all_market_data)} unique betting opportunities.")
        if requests_remaining:
            print(f"🔑 API Quota: {requests_remaining} requests remaining")

    if not all_market_data:
        # Complete scan session even if no data
        if scan_id and CACHING_ENABLED:
            try:
                scan_duration_ms = int((time.time() - scan_start_time) * 1000)
                odds_cache.complete_scan_session(
                    scan_id=scan_id,
                    total_events=len(event_info),
                    total_markets=0,
                    total_book_odds=0,
                    api_remaining=requests_remaining,
                    scan_duration_ms=scan_duration_ms
                )
            except Exception as e:
                if verbose:
                    print(f"⚠️ Cache completion error: {e}")
        return pd.DataFrame(), requests_remaining

    # Cache raw odds data before analysis
    scan_timestamp = datetime.now(timezone.utc)
    odds_snapshots_to_cache = []
    total_book_odds = 0

    if scan_id and CACHING_ENABLED:
        try:
            for bet_id, data in all_market_data.items():
                parts = bet_id.split('|')
                if len(parts) != 5:
                    continue

                player, market_key, line_str, side, evt_id = parts
                line = float(line_str) if line_str else 0

                if evt_id not in event_info:
                    continue

                evt = event_info[evt_id]
                market_name = format_market_name(market_key)
                minutes_to_game = int((evt['commence_time'] - scan_timestamp).total_seconds() / 60)

                # Cache each book's odds for this bet
                for book_abbrev, book_data in data.items():
                    if book_abbrev == 'market_key':
                        continue

                    total_book_odds += 1
                    odds_snapshots_to_cache.append({
                        'scan_id': scan_id,
                        'scan_timestamp': scan_timestamp.isoformat(),
                        'event_id': evt_id,
                        'home_team': evt['home_team'],
                        'away_team': evt['away_team'],
                        'commence_time': evt['commence_time'].isoformat(),
                        'minutes_to_game': minutes_to_game,
                        'market_key': market_key,
                        'market_name': market_name,
                        'player': player,
                        'line': line,
                        'side': side,
                        'book_key': '',  # We don't have the original key here
                        'book_abbrev': book_abbrev,
                        'odds': book_data['price'],
                        'link': book_data.get('link', ''),
                        'bet_id': bet_id,
                    })

            # Batch insert all raw odds
            if odds_snapshots_to_cache:
                odds_cache.batch_cache_odds(odds_snapshots_to_cache)
                if verbose:
                    print(f"💾 Cached {len(odds_snapshots_to_cache)} raw odds snapshots")
        except Exception as e:
            if verbose:
                print(f"⚠️ Raw odds caching error: {e}")

    # Build opposite side lookup (exactly like MKB)
    if verbose:
        print("   Building two-way market lookup...")

    opposite_lookup = {}

    for bet_id, data in all_market_data.items():
        parts = bet_id.split('|')
        if len(parts) != 5:
            continue

        player, market_key, line, side, evt_id = parts

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

        opp_bet_id = f"{player}|{market_key}|{line}|{opp_side}|{evt_id}"

        if opp_bet_id in all_market_data:
            opp_book_odds = {k: v for k, v in all_market_data[opp_bet_id].items() if k != 'market_key'}
            opposite_lookup[bet_id] = opp_book_odds

    if verbose:
        print(f"   Found {len(opposite_lookup)} two-way pairs")

    # Analyze opportunities
    opportunities = []
    markets_to_cache = []  # For caching aggregated market data

    for bet_id, data in all_market_data.items():
        parts = bet_id.split('|')
        if len(parts) != 5:
            continue

        player, market_key, line, side, evt_id = parts
        line = float(line) if line else 0

        if evt_id not in event_info:
            continue

        evt = event_info[evt_id]
        market_name = format_market_name(market_key)

        # Extract book odds (exclude 'market_key' entry)
        book_odds = {k: v for k, v in data.items() if k != 'market_key'}

        if not book_odds:
            continue

        # Sort books by price (highest first)
        sorted_prices = sorted(
            [(abbrev, d['price']) for abbrev, d in book_odds.items()],
            key=lambda x: x[1],
            reverse=True
        )

        if not sorted_prices:
            continue

        best_book, best_odds = sorted_prices[0]
        best_link_data = book_odds[best_book].get('link_data', {})
        best_link = book_odds[best_book].get('link', '')  # Raw link fallback
        coverage = len(book_odds)

        # Get opposite side odds
        opp_odds = opposite_lookup.get(bet_id, None)

        # Calculate fair probability (MKB methodology)
        fair_prob, calc_type = calculate_fair_probability(book_odds, opp_odds, market_key)

        # Skip bets where we couldn't calculate fair value (e.g., only exchange data)
        if calc_type == 'none':
            continue

        fair_odds = probability_to_american(fair_prob)

        # Decimal odds for calculations
        if best_odds > 0:
            decimal_odds = (best_odds / 100) + 1
        else:
            decimal_odds = (100 / abs(best_odds)) + 1

        # EV and Kelly
        ev_pct = calculate_ev_percentage(fair_prob, decimal_odds)

        if ev_pct > 0:
            std_kelly = calculate_kelly(ev_pct / 100, decimal_odds, fraction=0.25)
        else:
            std_kelly = 0.0

        conf_multiplier = get_confidence_multiplier(coverage)
        conf_kelly = std_kelly * conf_multiplier

        # Percent vs next best
        pct_vs_next, is_outlier = calculate_percent_vs_next(sorted_prices)

        # Get next best book info for debugging
        next_best_book = ''
        next_best_odds = 0
        if len(sorted_prices) >= 2:
            next_best_book = sorted_prices[1][0]
            next_best_odds = sorted_prices[1][1]

        # Game time formatting
        game_date, game_time = format_game_time(evt['commence_time'])

        # Best books string
        best_books_list = [abbrev for abbrev, price in sorted_prices if price == best_odds]
        best_books_str = ', '.join(best_books_list)

        # Determine alert tier for best odds
        alert_tier = None
        for tier, thresholds in ALERT_THRESHOLDS.items():
            if conf_kelly < thresholds.get('min_kelly', 0):
                continue
            if coverage < thresholds.get('min_coverage', 0):
                continue
            if 'min_odds' in thresholds and best_odds < thresholds['min_odds']:
                continue
            if 'min_pct_vs_next' in thresholds and not is_outlier:
                continue
            alert_tier = tier
            break

        # Calculate per-book metrics for state filtering
        per_book_metrics = {}
        qualifying_books_by_tier = {tier: [] for tier in ALERT_THRESHOLDS.keys()}

        for book_abbrev, book_data in book_odds.items():
            book_price = book_data['price']

            # Calculate THIS book's decimal odds
            if book_price > 0:
                book_decimal = (book_price / 100) + 1
            else:
                book_decimal = (100 / abs(book_price)) + 1

            # Calculate THIS book's EV
            book_ev = calculate_ev_percentage(fair_prob, book_decimal)

            if book_ev <= 0:
                continue

            # Calculate THIS book's Kelly
            book_std_kelly = calculate_kelly(book_ev / 100, book_decimal, fraction=0.25)
            book_conf_kelly = book_std_kelly * conf_multiplier

            per_book_metrics[book_abbrev] = {
                'odds': book_price,
                'ev_pct': round(book_ev, 2),
                'kelly': round(book_std_kelly, 4),
                'conf_kelly': round(book_conf_kelly, 4),
                'link': book_data.get('link', '')
            }

            # Check tier qualification for this book
            for tier, thresholds in ALERT_THRESHOLDS.items():
                if book_conf_kelly < thresholds.get('min_kelly', 0):
                    continue
                if coverage < thresholds.get('min_coverage', 0):
                    continue
                if 'min_odds' in thresholds and book_price < thresholds['min_odds']:
                    continue
                if 'min_pct_vs_next' in thresholds and not is_outlier:
                    continue
                qualifying_books_by_tier[tier].append(book_abbrev)

        # Build record
        record = {
            'Player': player,
            'Game': evt['game'],
            'Game Date': game_date,
            'Game Time': game_time,
            'Market': market_name,
            'Side': side,
            'Line': line if line else '',
            'Best Books': best_books_str,
            'Best Odds': int(best_odds),
            'Fair Odds': int(fair_odds),
            'EV %': round(ev_pct, 2),
            'Conf. Adj. Recc. U': round(conf_kelly, 4),
            'Std. Recc. U': round(std_kelly, 4),
            '% vs Next': round(pct_vs_next, 2),
            'Coverage': coverage,
            'Calc Type': calc_type,
            'Alert Tier': alert_tier,
            '_link_data': best_link_data,  # Multi-state link info for best book
            '_link': best_link,  # Raw link string fallback
            '_market_key': market_key,
            '_qualifying_books': qualifying_books_by_tier,
            '_book_odds': book_odds,
            '_per_book_metrics': per_book_metrics,
            '_next_best_book': next_best_book,
            '_next_best_odds': next_best_odds,
        }

        # Add individual book odds columns
        for book_abbrev in BOOK_ORDER:
            if book_abbrev in book_odds:
                record[book_abbrev] = int(book_odds[book_abbrev]['price'])
            else:
                record[book_abbrev] = ''

        opportunities.append(record)

        # Cache market snapshot (aggregated data with fair values)
        if scan_id and CACHING_ENABLED:
            try:
                # Get all book odds as dict for storage
                all_book_odds_dict = {k: v['price'] for k, v in book_odds.items()}

                markets_to_cache.append({
                    'scan_id': scan_id,
                    'scan_timestamp': scan_timestamp.isoformat(),
                    'event_id': evt_id,
                    'home_team': evt['home_team'],
                    'away_team': evt['away_team'],
                    'commence_time': evt['commence_time'].isoformat(),
                    'minutes_to_game': int((evt['commence_time'] - scan_timestamp).total_seconds() / 60),
                    'bet_id': bet_id,
                    'market_key': market_key,
                    'market_name': market_name,
                    'player': player,
                    'line': line,
                    'side': side,
                    'best_odds': int(best_odds),
                    'best_books': best_books_str,
                    'next_best_odds': int(next_best_odds) if next_best_odds else None,
                    'next_best_book': next_best_book,
                    'pct_vs_next': round(pct_vs_next, 2),
                    'fair_prob': round(fair_prob, 6),
                    'fair_odds': int(fair_odds),
                    'calc_type': calc_type,
                    'coverage': coverage,
                    'ev_pct': round(ev_pct, 2),
                    'std_kelly': round(std_kelly, 4),
                    'conf_kelly': round(conf_kelly, 4),
                    'alert_tier': alert_tier,
                    'all_book_odds': all_book_odds_dict,
                })
            except Exception:
                pass  # Silently skip caching errors for individual records

    # Cache all market snapshots
    if scan_id and CACHING_ENABLED and markets_to_cache:
        try:
            odds_cache.batch_cache_markets(markets_to_cache)
            if verbose:
                print(f"💾 Cached {len(markets_to_cache)} market snapshots with fair values")
        except Exception as e:
            if verbose:
                print(f"⚠️ Market caching error: {e}")

    # Complete scan session
    if scan_id and CACHING_ENABLED:
        try:
            scan_duration_ms = int((time.time() - scan_start_time) * 1000)
            odds_cache.complete_scan_session(
                scan_id=scan_id,
                total_events=len(event_info),
                total_markets=len(all_market_data),
                total_book_odds=total_book_odds,
                api_remaining=requests_remaining,
                scan_duration_ms=scan_duration_ms
            )
        except Exception as e:
            if verbose:
                print(f"⚠️ Scan completion error: {e}")

    if not opportunities:
        if verbose:
            print("\n✅ Scan complete. No opportunities found.")
        return pd.DataFrame(), requests_remaining

    df = pd.DataFrame(opportunities)
    df = df.sort_values('Conf. Adj. Recc. U', ascending=False)

    if verbose:
        plus_ev_count = len(df[df['EV %'] > 0])
        two_way_count = len(df[df['Calc Type'] == '2-way'])
        one_way_count = len(df[df['Calc Type'] == '1-way'])
        print(f"\n📊 Total: {len(df)} | +EV: {plus_ev_count}")
        print(f"   Two-way: {two_way_count} | One-way: {one_way_count}")

    return df, requests_remaining


def get_alerts(df: pd.DataFrame) -> pd.DataFrame:
    """Filter DataFrame to only alertable opportunities."""
    if df.empty:
        return df
    return df[df['Alert Tier'].notna()].copy()


def format_alert_message(row: pd.Series) -> str:
    """Format a single bet as a Telegram-friendly message."""
    tier_emoji = {
        'FIRE': '🔥',
        'VALUE_LONGSHOT': '🎯',
        'OUTLIER': '⚡'
    }.get(row.get('Alert Tier', ''), '📊')

    msg = f"{tier_emoji} <b>{row['Player']}</b>\n"
    msg += f"📍 {row['Market']} {row['Side']}"
    if row['Line']:
        msg += f" {row['Line']}"
    msg += f"\n\n"
    msg += f"💵 <b>{int(row['Best Odds']):+d}</b> (Fair: {int(row['Fair Odds']):+d})\n"
    msg += f"📈 EV: {row['EV %']:.1f}% | Units: {row['Conf. Adj. Recc. U']:.2f}\n"

    # Add % vs Next for OUTLIER alerts to help debug
    tier = row.get('Alert Tier', '')
    pct_vs_next = row.get('% vs Next', 0)
    next_best_book = row.get('_next_best_book', '')
    next_best_odds = row.get('_next_best_odds', 0)
    if tier == 'OUTLIER' and pct_vs_next:
        msg += f"📚 {row['Best Books']} | Cov: {row['Coverage']}\n"
        msg += f"📊 vs Next: {next_best_book} {int(next_best_odds):+d} ({pct_vs_next:.1f}%)\n"
    else:
        msg += f"📚 {row['Best Books']} | Coverage: {row['Coverage']}\n"

    msg += f"🏀 {row['Game']}\n"
    msg += f"⏰ {row['Game Time']}\n"

    # Add bet links with multi-state support (NY, PA, NJ)
    link_data = row.get('_link_data', {})

    if link_data and link_data.get('is_state_dependent'):
        # State-dependent book - show links for all states
        desktop_links = link_data.get('desktop', {})
        mobile_links = link_data.get('mobile', {})
        separate_mobile = link_data.get('separate_mobile', False)

        if separate_mobile and isinstance(desktop_links, dict) and isinstance(mobile_links, dict):
            # FanDuel: Show separate Desktop and Mobile rows
            # Desktop links differ by state, mobile links are all the same
            desktop_parts = []
            for state in SUPPORTED_STATES:
                state_upper = state.upper()
                if state in desktop_links:
                    desktop_parts.append(f"<a href=\"{desktop_links[state]}\">{state_upper}</a>")

            if desktop_parts:
                msg += f"🖥️ Desktop: {' · '.join(desktop_parts)}\n"

            # Mobile links are identical for all states, just show one
            first_mobile_link = mobile_links.get(SUPPORTED_STATES[0], '')
            if first_mobile_link:
                msg += f"📱 <a href=\"{first_mobile_link}\">Mobile</a>"
        elif isinstance(desktop_links, dict):
            # BetRivers, BetMGM, BallyBet: Same link for desktop/mobile, show state options
            link_parts = []
            for state in SUPPORTED_STATES:
                state_upper = state.upper()
                if state in desktop_links:
                    link_parts.append(f"<a href=\"{desktop_links[state]}\">{state_upper}</a>")

            if link_parts:
                msg += f"🔗 {' · '.join(link_parts)}"
    else:
        # Non-state-dependent book (DK, CZ, PN, etc.) - single link
        # Try link_data dict first, then raw link string, then generic book URL
        desktop_link = link_data.get('desktop', '') if link_data else ''
        if not desktop_link:
            # Fallback to raw link string (safer for books like Caesars)
            desktop_link = row.get('_link', '')

        if desktop_link:
            msg += f"🔗 <a href=\"{desktop_link}\">Place Bet</a>"
        else:
            # Final fallback: use generic book URL if no deep link available
            best_books = row.get('Best Books', '')
            if best_books:
                first_book = best_books.split(',')[0].strip()
                fallback_url = get_book_url(first_book)
                if fallback_url:
                    msg += f"🔗 <a href=\"{fallback_url}\">Place Bet</a>"

    return msg


# =============================================================================
# STANDALONE EXECUTION
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("NBA VALUE SCANNER v10.0")
    print("=" * 60)

    state = input("Enter state (default: pa): ").strip() or 'pa'

    df, remaining = scan_for_opportunities(state=state, verbose=True)

    if df.empty:
        print("No opportunities found")
    else:
        alerts = get_alerts(df)

        print(f"\n{'='*60}")
        print(f"ALERTS ({len(alerts)} total)")
        print("=" * 60)

        for tier in ['FIRE', 'VALUE_LONGSHOT', 'OUTLIER']:
            tier_df = alerts[alerts['Alert Tier'] == tier]
            if not tier_df.empty:
                emoji = {'FIRE': '🔥', 'VALUE_LONGSHOT': '🎯', 'OUTLIER': '⚡'}[tier]
                print(f"\n{emoji} {tier} ({len(tier_df)})")
                print("-" * 40)
                for _, row in tier_df.head(5).iterrows():
                    print(format_alert_message(row))
                    print()
