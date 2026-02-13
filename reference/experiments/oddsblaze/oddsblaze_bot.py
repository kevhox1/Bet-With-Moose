#!/usr/bin/env python3
"""
OddsBlaze NBA Long Shot Scanner Bot
====================================
Real-time odds scanner using OddsBlaze API + Telegram alerts.
Full-featured bot matching production UI.

Run locally:
    pip install -r requirements.txt
    python oddsblaze_bot.py
"""

import os
import sys
import re
import json
import time
import asyncio
import logging
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Any, Tuple
from collections import defaultdict

import pytz

# Telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

# Disable link previews
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)

# =============================================================================
# CONFIGURATION
# =============================================================================

# OddsBlaze API
API_KEY = "917a2324-7c87-494d-8fcc-edcb31af7e23"
API_BASE_URL = "https://odds.oddsblaze.com/"
SGP_API_BASE_URL = "https://{sportsbook}.sgp.oddsblaze.com/"

# Dummy leg settings
DUMMY_LEG_ODDS_CEILING = -3000  # Only include legs at this odds or shorter

# Telegram (Test - direct to user)
TELEGRAM_BOT_TOKEN = "8433115695:AAHIY27eEnfKMaL-SsVQL5dXUKuewpSpm18"
TELEGRAM_CHAT_ID = "5892910630"

# Supported states for links
SUPPORTED_STATES = ['ny', 'pa', 'nj']
DEFAULT_STATE = "ny"

# Scanning Settings
SCAN_INTERVAL_SECONDS = 4

# Eastern timezone
ET = pytz.timezone('US/Eastern')

# Active hours - DISABLED for test bot (runs 24/7, controlled by /pause and /resume)
ACTIVE_HOURS_START = 0   # Midnight
ACTIVE_HOURS_END = 24    # Midnight (full 24 hours)

# Sportsbooks to scan
SPORTSBOOKS = [
    'draftkings', 'fanduel', 'fanduel-yourway', 'betmgm', 'caesars', 'betrivers',
    'fanatics', 'betparx', 'fliff', 'thescore', 'pinnacle', 'circa',
    'bet365', 'bally-bet', 'hard-rock', 'prophetx'
]

# Books excluded from best odds (sharp books - used for fair value/coverage only)
SHARP_BOOKS = ['pinnacle', 'circa']

# Alert thresholds
ALERT_THRESHOLDS = {
    'FIRE': {'min_kelly': 0.30, 'min_coverage': 8},
    'VALUE_LONGSHOT': {'min_kelly': 0.15, 'min_coverage': 5, 'min_odds': 500},
    'OUTLIER': {'min_kelly': 0.05, 'min_coverage': 3, 'min_pct_vs_next': 35},
}

# Book abbreviation mapping (OddsBlaze uses lowercase full names)
BOOK_ABBREV_MAP = {
    'draftkings': 'DK',
    'fanduel': 'FD',
    'betmgm': 'MG',
    'caesars': 'CZ',
    'betrivers': 'BR',
    'fanatics': 'FN',
    'betparx': 'BP',
    'fliff': 'FL',
    'thescore': 'TS',
    'pinnacle': 'PN',
    'circa': 'CI',
    'bet365': 'B3',
    'bally-bet': 'BB',
    'hard-rock': 'HR',
    'prophetx': 'PX',
    'fanduel-yourway': 'FDYW',
}

# Global weights (V10 Pinnacle-Optimized) - matches production exactly
# Note: Exchanges are NOT included in fair value calculation
GLOBAL_WEIGHTS = {
    'DK': 0.2027,
    'FD': 0.1599,
    'MG': 0.1580,
    'PN': 0.1328,
    'ES': 0.0883,
    'RK': 0.0828,
    'CZ': 0.0742,
    'BO': 0.0412,
    'BB': 0.0096,
    'BR': 0.0096,
    'FL': 0.0096,
    'FN': 0.0096,
    'RB': 0.0048,
    'BP': 0.0048,
    'CI': 0.0000,
    'TS': 0.0048,  # theScore - not in production, giving same as BP
    'B3': 0.0000,  # bet365 - coverage only
    'BB': 0.0096,  # Bally Bet - same as BetRivers (sister books)
    'HR': 0.0096,  # Hard Rock - retail book, similar to BetRivers
    # Exchanges - zero weight for fair value calculation
    'KA': 0.0000,
    'NV': 0.0000,
    'PX': 0.0000,
    'BY': 0.0000,
    'FDYW': 0.0000,  # FanDuel YourWay - no weight (not independent from FanDuel)
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
    'player_double_double': 0.79,
    'player_triple_double': 0.70,
    'player_first_basket': 0.81,
    'player_first_team_basket': 0.82,
    'player_threes': 0.76,
    'player_rebounds': 0.79,
    'player_points': 0.76,
    'player_assists': 0.79,
    'player_steals': 0.85,
    'player_blocks': 0.87,
    'player_blocks_steals': 0.88,
    'player_points_rebounds_assists': 0.88,
    'player_rebounds_assists': 0.88,
    'player_points_rebounds': 0.88,
    'player_points_assists': 0.88,
}

# Longshot-specific multipliers for 1-way markets at +1000-2999
LONGSHOT_MARKET_MULTIPLIERS = {
    'player_points': 0.76,
    'player_points_alternate': 0.76,
    'player_threes': 0.76,
    'player_threes_alternate': 0.76,
    'player_assists': 0.79,
    'player_assists_alternate': 0.79,
    'player_rebounds': 0.79,
    'player_rebounds_alternate': 0.79,
    'player_steals': 0.85,
    'player_steals_alternate': 0.85,
    'player_blocks': 0.87,
    'player_blocks_alternate': 0.87,
    'player_double_double': 0.79,
    'player_triple_double': 0.70,
}

# Extreme longshot multipliers for +3000 and higher
EXTREME_LONGSHOT_MULTIPLIERS = {
    'player_points': 0.70,
    'player_points_alternate': 0.70,
    'player_threes': 0.70,
    'player_threes_alternate': 0.70,
    'player_assists': 0.72,
    'player_assists_alternate': 0.72,
    'player_rebounds': 0.74,
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

# Confidence multipliers based on book coverage (matches production)
CONFIDENCE_MULTIPLIERS = {
    1: 0.25, 2: 0.35, 3: 0.47, 4: 0.47, 5: 0.53,
    6: 0.56, 7: 0.62, 8: 0.70, 9: 0.72, 10: 0.81,
    11: 0.81, 12: 0.91, 13: 0.96, 14: 1.00, 15: 1.00,
}


def get_confidence_multiplier(coverage: int) -> float:
    """Get confidence multiplier based on book coverage."""
    if coverage >= 15:
        return 1.0
    return CONFIDENCE_MULTIPLIERS.get(coverage, 0.50)


# Book display config
BOOK_CONFIG = {
    'draftkings': {'abbrev': 'DK', 'name': 'DraftKings'},
    'fanduel': {'abbrev': 'FD', 'name': 'FanDuel'},
    'betmgm': {'abbrev': 'MG', 'name': 'BetMGM'},
    'caesars': {'abbrev': 'CZ', 'name': 'Caesars'},
    'betrivers': {'abbrev': 'BR', 'name': 'BetRivers'},
    'fanatics': {'abbrev': 'FN', 'name': 'Fanatics'},
    'betparx': {'abbrev': 'BP', 'name': 'BetParx'},
    'fliff': {'abbrev': 'FL', 'name': 'Fliff'},
    'thescore': {'abbrev': 'TS', 'name': 'theScore'},
    'pinnacle': {'abbrev': 'PN', 'name': 'Pinnacle'},
    'circa': {'abbrev': 'CI', 'name': 'Circa'},
    'bet365': {'abbrev': 'B3', 'name': 'bet365'},
    'bally-bet': {'abbrev': 'BB', 'name': 'Bally Bet'},
    'hard-rock': {'abbrev': 'HR', 'name': 'Hard Rock'},
    'prophetx': {'abbrev': 'PX', 'name': 'ProphetX'},
    'fanduel-yourway': {'abbrev': 'FDYW', 'name': 'FanDuel YourWay'},
}

# Sister books - when one has best odds, show both links
SISTER_BOOKS = {
    'betrivers': 'bally-bet',
    'bally-bet': 'betrivers',
}

# State-dependent books - need different URLs per state
STATE_DEPENDENT_BOOKS = {
    'fanduel': {
        'detect': ['sportsbook.fanduel.com'],
        'separate_mobile': True,
    },
    'betrivers': {
        'detect': ['betrivers.com'],
        'separate_mobile': False,
    },
    'betmgm': {
        'detect': ['betmgm.com', 'betmgm.ca'],  # OddsBlaze returns Canadian links
        'separate_mobile': False,
    },
    'caesars': {
        'detect': ['caesars.com'],
        'separate_mobile': False,
    },
}


# Market abbreviations for dummy leg display
MARKET_ABBREV = {
    'Player Points': 'Pts',
    'Player Rebounds': 'Reb',
    'Player Assists': 'Ast',
    'Player Threes': '3s',
    'Player Blocks': 'Blk',
    'Player Steals': 'Stl',
    'Player Double Double': 'DD',
    'Player Triple Double': 'TD',
    'Player Points Rebounds Assists': 'PRA',
    'Player Points Rebounds': 'P+R',
    'Player Points Assists': 'P+A',
    'Player Rebounds Assists': 'R+A',
    'Player Blocks Steals': 'B+S',
    'First Basket': '1st Bsk',
    'First Team Basket': '1st Tm',
}

# NBA team abbreviations for compact display
NBA_TEAM_ABBREV = {
    'Atlanta Hawks': 'ATL', 'Boston Celtics': 'BOS', 'Brooklyn Nets': 'BKN',
    'Charlotte Hornets': 'CHA', 'Chicago Bulls': 'CHI', 'Cleveland Cavaliers': 'CLE',
    'Dallas Mavericks': 'DAL', 'Denver Nuggets': 'DEN', 'Detroit Pistons': 'DET',
    'Golden State Warriors': 'GSW', 'Houston Rockets': 'HOU', 'Indiana Pacers': 'IND',
    'LA Clippers': 'LAC', 'Los Angeles Clippers': 'LAC',
    'Los Angeles Lakers': 'LAL', 'LA Lakers': 'LAL',
    'Memphis Grizzlies': 'MEM', 'Miami Heat': 'MIA', 'Milwaukee Bucks': 'MIL',
    'Minnesota Timberwolves': 'MIN', 'New Orleans Pelicans': 'NOP',
    'New York Knicks': 'NYK', 'Oklahoma City Thunder': 'OKC', 'Orlando Magic': 'ORL',
    'Philadelphia 76ers': 'PHI', 'Phoenix Suns': 'PHX', 'Portland Trail Blazers': 'POR',
    'Sacramento Kings': 'SAC', 'San Antonio Spurs': 'SAS', 'Toronto Raptors': 'TOR',
    'Utah Jazz': 'UTA', 'Washington Wizards': 'WAS',
}


def clean_link(link: str, book: str) -> str:
    """Clean up book links."""
    if not link:
        return link
    # State-dependent books are handled by generate_multi_state_links
    return link

# =============================================================================
# LOGGING
# =============================================================================

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('oddsblaze_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =============================================================================
# GLOBALS
# =============================================================================

sent_alerts: Dict[str, dict] = {}  # alert_key -> {ev_pct, timestamp}
pending_alerts: Dict[str, dict] = {}  # For "Show More" functionality
auto_scan_enabled = True
current_state = DEFAULT_STATE
active_tiers: Set[str] = {'FIRE', 'VALUE_LONGSHOT', 'OUTLIER'}
is_paused = False
scan_interval = SCAN_INTERVAL_SECONDS  # Can be changed via /resume
force_next_scan = False  # When True, bypass active hours check for one scan

# Custom filter settings (for CUSTOM tier)
custom_filter = {
    'min_ev': 10.0,
    'min_kelly': 0.5,
    'min_odds': 100,
}
use_custom_filter = False  # True when CUSTOM tier is active

# Selected books for alerts (empty list = all retail books)
# Retail books only - excludes sharp books used for coverage
RETAIL_BOOKS = ['DK', 'FD', 'FDYW', 'MG', 'CZ', 'BR', 'FN', 'BP', 'FL', 'TS', 'B3', 'BB', 'HR']
selected_books: List[str] = []  # Empty means all retail books

# Track last reset date for midnight clearing
last_reset_date: Optional[str] = None

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def american_to_probability(odds: int) -> float:
    """Convert American odds to implied probability."""
    if odds == 0:
        return 0.0
    if odds > 0:
        return 100 / (odds + 100)
    else:
        return abs(odds) / (abs(odds) + 100)


def probability_to_american(prob: float) -> int:
    """Convert probability to American odds."""
    if prob <= 0 or prob >= 1:
        return 0
    if prob >= 0.5:
        return int(-100 * prob / (1 - prob))
    else:
        return int(100 * (1 - prob) / prob)


def parse_american_odds(price_str: str) -> int:
    """Parse American odds string to int."""
    try:
        price_str = str(price_str).strip()
        if price_str.startswith('+'):
            return int(price_str[1:])
        return int(price_str)
    except:
        return 0


def format_american_odds(odds: int) -> str:
    """Format American odds with +/- sign."""
    if odds > 0:
        return f"+{odds}"
    return str(odds)


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


def generate_multi_state_links(link: str, book: str) -> dict:
    """Generate links for all supported states from a base link."""
    if not link:
        return {
            'book': book,
            'is_state_dependent': False,
            'separate_mobile': False,
            'desktop': '',
            'mobile': '',
        }

    book_lower = book.lower()
    book_config = STATE_DEPENDENT_BOOKS.get(book_lower)

    if not book_config:
        return {
            'book': book,
            'is_state_dependent': False,
            'separate_mobile': False,
            'desktop': link,
            'mobile': link,
        }

    # Check if any of the detect patterns match
    detect_patterns = book_config['detect']
    matched = any(pattern in link for pattern in detect_patterns)

    if not matched:
        return {
            'book': book,
            'is_state_dependent': False,
            'separate_mobile': False,
            'desktop': link,
            'mobile': link,
        }

    if book_lower == 'fanduel':
        desktop_links = {}
        mobile_links = {}
        path_match = re.search(r'sportsbook\.fanduel\.com(/.*)?$', link)
        path = path_match.group(1) if path_match and path_match.group(1) else ''

        for state in SUPPORTED_STATES:
            desktop_links[state] = f"https://{state}.sportsbook.fanduel.com{path}"
            mobile_links[state] = f"https://sportsbook.fanduel.com{path}"

        return {
            'book': book,
            'is_state_dependent': True,
            'separate_mobile': True,
            'desktop': desktop_links,
            'mobile': mobile_links,
        }

    elif book_lower == 'betrivers':
        state_links = {}
        path_match = re.search(r'betrivers\.com(/.*)?$', link)
        path = path_match.group(1) if path_match and path_match.group(1) else ''
        for state in SUPPORTED_STATES:
            state_links[state] = f"https://{state}.betrivers.com{path}"

        return {
            'book': book,
            'is_state_dependent': True,
            'separate_mobile': False,
            'desktop': state_links,
            'mobile': state_links,
        }

    elif book_lower == 'betmgm':
        state_links = {}
        # Handle both .com and .ca domains (OddsBlaze returns Canadian links)
        # Example: https://sports.on.betmgm.ca/en/sports/events/123?options=...
        # Convert to: https://sports.ny.betmgm.com/en/sports/events/123?options=...
        path_match = re.search(r'betmgm\.(?:com|ca)(/.*)?$', link)
        path = path_match.group(1) if path_match and path_match.group(1) else ''

        for state in SUPPORTED_STATES:
            state_links[state] = f"https://sports.{state}.betmgm.com{path}"

        return {
            'book': book,
            'is_state_dependent': True,
            'separate_mobile': False,
            'desktop': state_links,
            'mobile': state_links,
        }

    elif book_lower == 'caesars':
        state_links = {}
        # Example: https://sportsbook.caesars.com/us/mi/bet/betslip?selectionIds=...
        # Convert to: https://sportsbook.caesars.com/us/ny/bet/betslip?selectionIds=...
        for state in SUPPORTED_STATES:
            # Replace /us/{any_state}/ with /us/{state}/
            state_link = re.sub(r'/us/[a-z]{2}/', f'/us/{state}/', link)
            state_links[state] = state_link

        return {
            'book': book,
            'is_state_dependent': True,
            'separate_mobile': False,
            'desktop': state_links,
            'mobile': state_links,
        }

    return {
        'book': book,
        'is_state_dependent': False,
        'separate_mobile': False,
        'desktop': link,
        'mobile': link,
    }


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
    for book_name, data in book_odds.items():
        odds = data['price']
        implied_prob = american_to_probability(odds)

        if implied_prob <= 0:
            continue

        # Map book name to abbreviation for weight lookup
        book_abbrev = BOOK_ABBREV_MAP.get(book_name.lower(), book_name.upper()[:2])
        weight = GLOBAL_WEIGHTS.get(book_abbrev, 0.01)

        # Check if this specific book has the opposite side
        has_opposite = opposite_odds and book_name in opposite_odds

        if has_opposite:
            # TWO-WAY: This book has both sides - use proportional de-vig
            opp_prob = american_to_probability(opposite_odds[book_name]['price'])

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


def calculate_kelly(edge: float, decimal_odds: float, fraction: float = 0.25) -> float:
    """Calculate Kelly stake (Quarter Kelly by default) - matches production."""
    if decimal_odds <= 1 or edge <= 0:
        return 0.0
    kelly_full = edge / (decimal_odds - 1)
    kelly_fractional = kelly_full * fraction
    return kelly_fractional * 100  # Return as units


def calculate_ev_percentage(fair_prob: float, best_odds: int) -> float:
    """Calculate expected value percentage."""
    if fair_prob <= 0 or best_odds == 0:
        return 0.0

    if best_odds > 0:
        decimal_odds = (best_odds / 100) + 1
    else:
        decimal_odds = (100 / abs(best_odds)) + 1

    ev = (fair_prob * decimal_odds) - 1
    return ev * 100


def is_active_hours() -> bool:
    """Check if current time is within active betting hours."""
    now_et = datetime.now(ET)
    hour = now_et.hour
    if ACTIVE_HOURS_START > ACTIVE_HOURS_END:
        return hour >= ACTIVE_HOURS_START or hour < ACTIVE_HOURS_END
    else:
        return ACTIVE_HOURS_START <= hour < ACTIVE_HOURS_END


# =============================================================================
# ODDSBLAZE API
# =============================================================================

def fetch_odds_for_sportsbook(sportsbook: str) -> Optional[dict]:
    """Fetch NBA odds from OddsBlaze for a specific sportsbook."""
    try:
        url = f"{API_BASE_URL}?key={API_KEY}&sportsbook={sportsbook}&league=nba"
        response = requests.get(url, timeout=30)

        if response.status_code == 200:
            return response.json()
        else:
            logger.warning(f"Failed to fetch {sportsbook}: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Error fetching {sportsbook}: {e}")
        return None


def fetch_all_odds() -> Dict[str, dict]:
    """Fetch odds from all sportsbooks."""
    all_odds = {}

    for book in SPORTSBOOKS:
        data = fetch_odds_for_sportsbook(book)
        if data and 'events' in data:
            all_odds[book] = data
            logger.info(f"Fetched {book}: {len(data['events'])} events")

    return all_odds


def aggregate_player_props(all_odds: Dict[str, dict]) -> Dict[str, dict]:
    """Aggregate player props across all sportsbooks."""
    props = defaultdict(lambda: {'books': {}, 'player': None, 'market': None, 'event': None})

    for book, data in all_odds.items():
        book_lower = book.lower()

        for event in data.get('events', []):
            event_info = {
                'id': event.get('id'),
                'teams': event.get('teams'),
                'date': event.get('date'),
                'live': event.get('live', False)
            }

            if event_info['live']:
                continue

            for odd in event.get('odds', []):
                market = odd.get('market', '')

                if 'Player' not in market and 'First Basket' not in market:
                    continue

                selection = odd.get('selection', {})
                player_name = selection.get('name', '')
                line = selection.get('line', '')
                side = selection.get('side', 'Over')

                if not player_name:
                    player_info = odd.get('player', {})
                    player_name = player_info.get('name', 'Unknown')

                # IMPORTANT: Always include side to avoid mixing YES/NO odds
                if line:
                    prop_key = f"{player_name}|{market}|{side} {line}"
                else:
                    prop_key = f"{player_name}|{market}|{side}"

                price = parse_american_odds(odd.get('price', '0'))
                if price == 0:
                    continue

                links = odd.get('links', {})
                link = links.get('desktop', '')

                props[prop_key]['books'][book_lower] = {
                    'price': price,
                    'link': link,
                    'main': odd.get('main', False),
                    'sgp': odd.get('sgp', ''),
                }
                props[prop_key]['player'] = player_name
                props[prop_key]['market'] = market
                props[prop_key]['selection'] = selection
                props[prop_key]['event'] = event_info

    return dict(props)


# =============================================================================
# SCANNING & ALERTS
# =============================================================================

def market_to_key(market: str) -> str:
    """Convert display market name to API-style key for multiplier lookup."""
    # "Player Double Double" -> "player_double_double"
    return market.lower().replace(' ', '_').replace('+', '')


# =============================================================================
# DUMMY LEGS & SGP HELPERS
# =============================================================================

def extract_stat_categories(market: str) -> set:
    """Extract stat categories from market name for anti-correlation checking.

    Returns a set of stat categories (e.g., {'points'}, {'rebounds', 'assists'}).
    Used to avoid correlated dummy legs (same player + same stat).
    """
    market_lower = market.lower()
    cats = set()
    if 'point' in market_lower:
        cats.add('points')
    if 'rebound' in market_lower:
        cats.add('rebounds')
    if 'assist' in market_lower:
        cats.add('assists')
    if 'three' in market_lower:
        cats.add('threes')
    if 'block' in market_lower:
        cats.add('blocks')
    if 'steal' in market_lower:
        cats.add('steals')
    if 'double double' in market_lower:
        cats.add('double_double')
    if 'triple double' in market_lower:
        cats.add('triple_double')
    if 'first basket' in market_lower or 'first team basket' in market_lower:
        cats.add('first_basket')
    return cats if cats else {'other'}


def abbreviate_player(name: str) -> str:
    """Shorten player name: 'Jayson Tatum' -> 'J. Tatum'."""
    parts = name.split()
    if len(parts) >= 2:
        return f"{parts[0][0]}. {' '.join(parts[1:])}"
    return name


def abbreviate_market(market: str) -> str:
    """Get short market name for display."""
    return MARKET_ABBREV.get(market, market.replace('Player ', ''))


def abbreviate_team(full_name: str) -> str:
    """Get NBA team abbreviation: 'Los Angeles Lakers' -> 'LAL'."""
    return NBA_TEAM_ABBREV.get(full_name, full_name.split()[-1][:3].upper())


def find_dummy_legs(opp: dict, props: dict, max_same_game: int = 4, max_other_game: int = 4) -> dict:
    """Find short DraftKings dummy legs for SGP/parlay building.

    Finds the shortest (most heavily favored) DK alternate player prop legs
    from the same game and other games, avoiding correlated legs.

    Args:
        opp: The alert opportunity dict
        props: Full props dict from the scan
        max_same_game: Max same-game dummy legs to return
        max_other_game: Max other-game dummy legs (1 per unique game)

    Returns:
        {'same_game': [leg_dicts], 'other_games': [leg_dicts]}
    """
    alert_event_id = opp.get('event', {}).get('id')
    alert_player = opp.get('player', '')
    alert_prop_key = opp.get('prop_key', '')
    alert_stat_cats = extract_stat_categories(opp.get('market', ''))

    same_game_candidates = []
    other_game_candidates = []

    for prop_key, prop_data in props.items():
        # Skip the alert's own prop
        if prop_key == alert_prop_key:
            continue

        dk_data = prop_data['books'].get('draftkings')
        if not dk_data:
            continue

        dk_price = dk_data['price']

        # Only consider very short legs (more negative than ceiling)
        if dk_price > DUMMY_LEG_ODDS_CEILING:
            continue

        prop_player = prop_data.get('player', '')
        prop_market = prop_data.get('market', '')
        prop_event = prop_data.get('event', {})
        prop_event_id = prop_event.get('id')
        prop_stat_cats = extract_stat_categories(prop_market)

        # Anti-correlation: skip if same player AND overlapping stat category
        if prop_player == alert_player and prop_stat_cats & alert_stat_cats:
            continue

        leg_info = {
            'prop_key': prop_key,
            'player': prop_player,
            'market': prop_market,
            'selection': prop_data.get('selection', {}),
            'event': prop_event,
            'dk_price': dk_price,
            'dk_link': dk_data.get('link', ''),
            'dk_sgp': dk_data.get('sgp', ''),
        }

        if prop_event_id == alert_event_id:
            same_game_candidates.append(leg_info)
        else:
            other_game_candidates.append(leg_info)

    # Sort by shortest odds (most negative first)
    same_game_candidates.sort(key=lambda x: x['dk_price'])
    other_game_candidates.sort(key=lambda x: x['dk_price'])

    # Pick top same-game legs
    same_game_legs = same_game_candidates[:max_same_game]

    # Pick top other-game legs (1 per unique game)
    other_game_legs = []
    seen_games = set()
    for leg in other_game_candidates:
        event_id = leg['event'].get('id')
        if event_id and event_id not in seen_games:
            other_game_legs.append(leg)
            seen_games.add(event_id)
            if len(other_game_legs) >= max_other_game:
                break

    return {
        'same_game': same_game_legs,
        'other_games': other_game_legs,
    }


def fetch_sgp_price(sportsbook: str, sgp_ids: list) -> dict:
    """Call OddsBlaze BlazeBuilder API to get SGP combined price and deep links.

    Args:
        sportsbook: Sportsbook ID (e.g., 'draftkings')
        sgp_ids: List of SGP identifier strings from odds objects

    Returns:
        {'price': '+425', 'links': {'desktop': 'url', 'mobile': 'url'}} on success
        {'error': 'message'} on failure
    """
    if not sgp_ids or any(not s for s in sgp_ids):
        return {'error': 'Missing SGP identifiers'}

    url = f"{SGP_API_BASE_URL.format(sportsbook=sportsbook)}?key={API_KEY}"

    try:
        response = requests.post(url, json=sgp_ids, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if 'message' in data:
                return {'error': data['message']}
            return data
        else:
            return {'error': f'HTTP {response.status_code}'}
    except Exception as e:
        logger.error(f"SGP API error: {e}")
        return {'error': str(e)}


def build_sgp_links(main_sgp: str, same_game_legs: list) -> dict:
    """Build 3-leg and 5-leg SGP links via BlazeBuilder API.

    Returns:
        {
            '3_leg': {'price': '+480', 'links': {...}} or {'error': '...'},
            '5_leg': {'price': '+520', 'links': {...}} or {'error': '...'},
        }
    """
    result = {}

    # 3-leg SGP: main + 2 dummy legs
    if len(same_game_legs) >= 2:
        sgp_ids_3 = [main_sgp] + [leg['dk_sgp'] for leg in same_game_legs[:2]]
        if all(sgp_ids_3):
            result['3_leg'] = fetch_sgp_price('draftkings', sgp_ids_3)

    # 5-leg SGP: main + 4 dummy legs
    if len(same_game_legs) >= 4:
        sgp_ids_5 = [main_sgp] + [leg['dk_sgp'] for leg in same_game_legs[:4]]
        if all(sgp_ids_5):
            result['5_leg'] = fetch_sgp_price('draftkings', sgp_ids_5)

    return result


def enrich_dk_opportunity(opp: dict, props: dict) -> None:
    """Add dummy legs and SGP data to a DraftKings opportunity (in-place).

    Only enriches if best_book is 'draftkings' and not already enriched.
    """
    if opp.get('best_book') != 'draftkings':
        return
    if 'dummy_legs' in opp:
        return  # Already enriched

    dummy_legs = find_dummy_legs(opp, props)
    opp['dummy_legs'] = dummy_legs

    # Try SGP links if we have same-game legs with sgp identifiers
    if dummy_legs['same_game']:
        main_sgp = opp.get('all_books', {}).get('draftkings', {}).get('sgp', '')
        if main_sgp:
            opp['sgp_data'] = build_sgp_links(main_sgp, dummy_legs['same_game'])


def build_opposite_lookup(props: Dict[str, dict]) -> Dict[str, Dict[str, Dict]]:
    """Build opposite side lookup for two-way de-vig (matches production exactly)."""
    opposite_lookup = {}

    for prop_key, prop_data in props.items():
        # Parse prop_key: "{player}|{market}|{side} {line}" or "{player}|{market}|{side}"
        parts = prop_key.split('|')
        if len(parts) != 3:
            continue

        player, market, side_line = parts

        # Parse side and line from "Over 25.5" or "Yes"
        side_parts = side_line.split(' ', 1)
        side = side_parts[0]
        line = side_parts[1] if len(side_parts) > 1 else ''

        # Determine opposite side
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

        # Build opposite prop_key
        if line:
            opp_key = f"{player}|{market}|{opp_side} {line}"
        else:
            opp_key = f"{player}|{market}|{opp_side}"

        # Check if opposite exists
        if opp_key in props:
            opposite_lookup[prop_key] = props[opp_key]['books']

    return opposite_lookup


def scan_for_value(props: Dict[str, dict], min_ev: float = 5.0, min_odds: int = 200) -> List[dict]:
    """Scan aggregated props for value opportunities using production methodology."""
    opportunities = []

    # Build opposite side lookup for two-way de-vig
    opposite_lookup = build_opposite_lookup(props)

    for prop_key, prop_data in props.items():
        books = prop_data['books']

        if len(books) < 2:
            continue

        # Sort books by price (highest first)
        sorted_prices = sorted(
            [(book, data['price']) for book, data in books.items()],
            key=lambda x: x[1],
            reverse=True
        )

        # Exclude sharp books from best odds selection
        retail_prices = [(b, p) for b, p in sorted_prices if b not in SHARP_BOOKS]
        if not retail_prices:
            retail_prices = sorted_prices

        best_book, best_odds = retail_prices[0]

        if best_odds < min_odds:
            continue

        market = prop_data['market']
        market_key = market_to_key(market)

        # Get opposite side odds for this prop
        opp_odds = opposite_lookup.get(prop_key, None)

        # Calculate fair probability using production methodology
        fair_prob, calc_type = calculate_fair_probability(books, opp_odds, market_key)

        # Skip if couldn't calculate fair value
        if calc_type == 'none' or fair_prob <= 0:
            continue

        # Calculate decimal odds
        if best_odds > 0:
            decimal_odds = (best_odds / 100) + 1
        else:
            decimal_odds = (100 / abs(best_odds)) + 1

        ev_pct = calculate_ev_percentage(fair_prob, best_odds)

        # Calculate Kelly (quarter Kelly, returns units) - matches production
        if ev_pct > 0:
            std_kelly = calculate_kelly(ev_pct / 100, decimal_odds, fraction=0.25)
        else:
            std_kelly = 0.0

        # Apply confidence multiplier based on coverage
        coverage = len(books)
        conf_multiplier = get_confidence_multiplier(coverage)
        conf_kelly = std_kelly * conf_multiplier

        fair_odds = probability_to_american(fair_prob)

        if ev_pct < min_ev:
            continue

        best_link = clean_link(books.get(best_book, {}).get('link', ''), best_book)

        # Get book prices for tier determination
        book_prices = {book: data['price'] for book, data in books.items()}

        # Use conf_kelly for tier determination (matches production)
        tier = determine_tier(conf_kelly, coverage, best_odds, book_prices)

        if tier:
            opportunities.append({
                'prop_key': prop_key,
                'player': prop_data['player'],
                'market': market,
                'selection': prop_data['selection'],
                'event': prop_data['event'],
                'best_book': best_book,
                'best_odds': best_odds,
                'best_link': best_link,
                'fair_odds': fair_odds,
                'ev_pct': ev_pct,
                'kelly': conf_kelly,  # Use confidence-adjusted Kelly (units)
                'std_kelly': std_kelly,  # Standard Kelly before confidence adjustment
                'coverage': coverage,
                'all_books': books,
                'tier': tier,
                'calc_type': calc_type,  # Track de-vig method used
            })

    opportunities.sort(key=lambda x: x['ev_pct'], reverse=True)
    return opportunities


def determine_tier(kelly: float, coverage: int, best_odds: int, book_prices: Dict[str, int]) -> Optional[str]:
    """Determine alert tier based on metrics."""
    fire = ALERT_THRESHOLDS['FIRE']
    if kelly >= fire['min_kelly'] and coverage >= fire['min_coverage']:
        return 'FIRE'

    value = ALERT_THRESHOLDS['VALUE_LONGSHOT']
    if kelly >= value['min_kelly'] and coverage >= value['min_coverage'] and best_odds >= value['min_odds']:
        return 'VALUE_LONGSHOT'

    outlier = ALERT_THRESHOLDS['OUTLIER']
    if kelly >= outlier['min_kelly'] and coverage >= outlier['min_coverage']:
        sorted_prices = sorted(book_prices.values(), reverse=True)
        if len(sorted_prices) >= 2:
            best = sorted_prices[0]
            next_best = sorted_prices[1]
            if next_best > 0:
                pct_diff = ((best - next_best) / next_best) * 100
                if pct_diff >= outlier['min_pct_vs_next']:
                    return 'OUTLIER'

    return None


def format_alert_message(opp: dict, repost_info: dict = None) -> str:
    """Format opportunity as Telegram alert message (matches production format)."""
    tier_emoji = {'FIRE': '🔥', 'VALUE_LONGSHOT': '🎯', 'OUTLIER': '⚡'}.get(opp['tier'], '📊')

    event = opp.get('event', {})
    teams = event.get('teams', {})
    away = teams.get('away', {}).get('name', 'Away')
    home = teams.get('home', {}).get('name', 'Home')
    game = f"{away} @ {home}"

    selection = opp.get('selection', {})
    line = selection.get('line', '')
    side = selection.get('side', '')

    market = opp['market'].replace('Player ', '')

    # Repost header if this is a resend
    msg = ""
    if repost_info:
        prev_odds = repost_info.get('prev_odds', 0)
        prev_kelly = repost_info.get('prev_kelly', 0)
        prev_time = repost_info.get('prev_time')

        time_str = ""
        if prev_time:
            # Convert to ET and format
            prev_time_et = prev_time.astimezone(ET)
            time_str = prev_time_et.strftime('%I:%M %p')

        msg += f"🔄 <b>REPOST</b> (was {format_american_odds(prev_odds)} @ {time_str})\n"

    msg += f"{tier_emoji} <b>{opp['player']}</b>\n"
    msg += f"📍 {market}"
    if side:
        msg += f" ({side})"
    if line:
        msg += f" {line}"
    msg += "\n\n"

    msg += f"💵 <b>{format_american_odds(opp['best_odds'])}</b> (Fair: {format_american_odds(opp['fair_odds'])})\n"
    msg += f"📈 EV: {opp['ev_pct']:.1f}% | Units: {opp['kelly']:.2f}\n"

    book_abbrev = BOOK_CONFIG.get(opp['best_book'], {}).get('abbrev', opp['best_book'].upper()[:2])
    msg += f"📚 {book_abbrev} | Coverage: {opp['coverage']}\n"

    msg += f"🏀 {game}\n"

    # Multi-state links
    best_link = opp.get('best_link', '')
    best_book = opp.get('best_book', '')
    link_data = generate_multi_state_links(best_link, best_book)

    if link_data.get('is_state_dependent'):
        desktop_links = link_data.get('desktop', {})
        mobile_links = link_data.get('mobile', {})
        separate_mobile = link_data.get('separate_mobile', False)

        if separate_mobile and isinstance(desktop_links, dict) and isinstance(mobile_links, dict):
            desktop_parts = []
            for state in SUPPORTED_STATES:
                state_upper = state.upper()
                if state in desktop_links:
                    desktop_parts.append(f"<a href=\"{desktop_links[state]}\">{state_upper}</a>")

            if desktop_parts:
                msg += f"🖥️ Desktop: {' · '.join(desktop_parts)}\n"

            first_mobile_link = mobile_links.get(SUPPORTED_STATES[0], '')
            if first_mobile_link:
                msg += f"📱 <a href=\"{first_mobile_link}\">Mobile</a>"
        elif isinstance(desktop_links, dict):
            link_parts = []
            for state in SUPPORTED_STATES:
                state_upper = state.upper()
                if state in desktop_links:
                    link_parts.append(f"<a href=\"{desktop_links[state]}\">{state_upper}</a>")

            if link_parts:
                msg += f"🔗 {' · '.join(link_parts)}"
    else:
        if best_link:
            msg += f"🔗 <a href=\"{best_link}\">Place Bet</a>"

    # Sister book link (BetRivers <-> Bally Bet)
    all_books = opp.get('all_books', {})
    sister_book = SISTER_BOOKS.get(best_book.lower())
    if sister_book and sister_book in all_books:
        sister_data = all_books[sister_book]
        sister_link = sister_data.get('link', '')
        sister_price = sister_data.get('price', 0)
        best_price = opp.get('best_odds', 0)

        # Show sister book if it has the same or similar odds (within 10 points)
        if sister_link and abs(sister_price - best_price) <= 10:
            sister_abbrev = BOOK_CONFIG.get(sister_book, {}).get('abbrev', sister_book.upper()[:2])
            sister_link_data = generate_multi_state_links(sister_link, sister_book)

            if sister_link_data.get('is_state_dependent'):
                # Multi-state links for BetRivers
                desktop_links = sister_link_data.get('desktop', {})
                if isinstance(desktop_links, dict):
                    link_parts = []
                    for state in SUPPORTED_STATES:
                        if state in desktop_links:
                            link_parts.append(f"<a href=\"{desktop_links[state]}\">{state.upper()}</a>")
                    if link_parts:
                        msg += f"\n🔗 {sister_abbrev}: {' · '.join(link_parts)}"
            else:
                # Simple link for Bally Bet
                msg += f"\n🔗 <a href=\"{sister_link}\">{sister_abbrev}</a>"

    # DEBUG: Add all book odds for comparison
    all_books = opp.get('all_books', {})
    if all_books:
        # Sort by price (highest first) and format with abbreviations
        sorted_odds = sorted(
            [(book, data['price']) for book, data in all_books.items()],
            key=lambda x: x[1],
            reverse=True
        )

        # Format as rows of 4 books each
        msg += f"\n\n<code>📊 All Odds ({len(sorted_odds)} books):\n"
        row_items = []
        for book, price in sorted_odds:
            abbrev = BOOK_ABBREV_MAP.get(book.lower(), book.upper()[:2])
            row_items.append(f"{abbrev:>2} {price:+d}")
            if len(row_items) == 4:
                msg += " | ".join(row_items) + "\n"
                row_items = []
        if row_items:
            msg += " | ".join(row_items)
        msg += "</code>"

    # DK Dummy Legs section (for DraftKings alerts with enriched data)
    dummy_legs = opp.get('dummy_legs')
    if dummy_legs:
        same_game = dummy_legs.get('same_game', [])
        other_games = dummy_legs.get('other_games', [])
        sgp_data = opp.get('sgp_data', {})

        if same_game:
            msg += f"\n\n🦵 <b>DK Same-Game Legs:</b>\n"
            for i, leg in enumerate(same_game, 1):
                player_short = abbreviate_player(leg['player'])
                market_short = abbreviate_market(leg['market'])
                sel = leg.get('selection', {})
                side = sel.get('side', '')
                line_val = sel.get('line', '')
                side_short = side[0] if side else ''  # O/U/Y/N
                line_str = f" {line_val}" if line_val else ""
                price_str = format_american_odds(leg['dk_price'])
                link = leg.get('dk_link', '')

                leg_text = f"{i}. {player_short} {side_short}{line_str} {market_short} ({price_str})"
                if link:
                    msg += f"  <a href=\"{link}\">{leg_text}</a>\n"
                else:
                    msg += f"  {leg_text}\n"

            # SGP links
            if sgp_data:
                for key, label in [('3_leg', '3-Leg'), ('5_leg', '5-Leg')]:
                    sgp_result = sgp_data.get(key)
                    if not sgp_result:
                        continue
                    if 'error' not in sgp_result:
                        price = sgp_result.get('price', '')
                        links = sgp_result.get('links', {})
                        desktop_link = links.get('desktop', '')
                        if desktop_link:
                            msg += f"🎰 <a href=\"{desktop_link}\">{label} SGP ({price})</a>\n"
                        else:
                            msg += f"🎰 {label} SGP: {price}\n"
                    else:
                        msg += f"🎰 {label} SGP: ❌ {sgp_result['error']}\n"

        if other_games:
            msg += f"\n🦵 <b>DK Other-Game Legs:</b>\n"
            for i, leg in enumerate(other_games, 1):
                player_short = abbreviate_player(leg['player'])
                market_short = abbreviate_market(leg['market'])
                sel = leg.get('selection', {})
                side = sel.get('side', '')
                line_val = sel.get('line', '')
                side_short = side[0] if side else ''
                line_str = f" {line_val}" if line_val else ""
                price_str = format_american_odds(leg['dk_price'])
                link = leg.get('dk_link', '')

                # Show game info for other games
                event = leg.get('event', {})
                teams = event.get('teams', {})
                away = abbreviate_team(teams.get('away', {}).get('name', '?'))
                home = abbreviate_team(teams.get('home', {}).get('name', '?'))
                game_str = f" ({away}@{home})"

                leg_text = f"{i}. {player_short} {side_short}{line_str} {market_short} ({price_str})"
                if link:
                    msg += f"  <a href=\"{link}\">{leg_text}</a>{game_str}\n"
                else:
                    msg += f"  {leg_text}{game_str}\n"

    return msg


def is_duplicate_alert(opp: dict) -> bool:
    """Check if alert is a duplicate. Only allow resend if Kelly increased by 0.10+ units."""
    alert_key = opp['prop_key']

    if alert_key not in sent_alerts:
        return False

    last_kelly = sent_alerts[alert_key]['kelly']
    current_kelly = opp['kelly']

    # Only resend if Kelly (recommended bet size) increased by 0.10 or more units
    if current_kelly >= last_kelly + 0.10:
        logger.info(f"Resending alert - Kelly increased: {last_kelly:.2f} -> {current_kelly:.2f} ({opp['player']} {opp['market']})")
        return False

    logger.debug(f"Blocked duplicate: {opp['player']} {opp['market']} (Kelly: {current_kelly:.2f}, prev: {last_kelly:.2f})")
    return True


def get_repost_info(opp: dict) -> dict:
    """Get previous alert info if this is a repost. Returns None if not a repost."""
    alert_key = opp['prop_key']

    if alert_key not in sent_alerts:
        return None

    prev = sent_alerts[alert_key]
    current_kelly = opp['kelly']
    last_kelly = prev['kelly']

    # It's a repost if Kelly increased by 0.10+ units
    if current_kelly >= last_kelly + 0.10:
        return {
            'prev_kelly': last_kelly,
            'prev_odds': prev.get('best_odds', 0),
            'prev_time': prev.get('timestamp'),
        }

    return None


def record_sent_alert(opp: dict):
    """Record that an alert was sent for deduplication tracking."""
    alert_key = opp['prop_key']
    sent_alerts[alert_key] = {
        'kelly': opp['kelly'],
        'ev_pct': opp['ev_pct'],
        'best_odds': opp['best_odds'],
        'timestamp': datetime.now(timezone.utc)
    }


async def send_alert(app: Application, opp: dict, props: dict = None) -> bool:
    """Send alert to Telegram (with deduplication and book filtering).

    Args:
        app: Telegram Application
        opp: Opportunity dict
        props: Full props dict for DK dummy leg enrichment (optional)
    """
    # Check if this book is in the selected books
    best_book = opp.get('best_book', '')
    book_abbrev = BOOK_CONFIG.get(best_book, {}).get('abbrev', best_book.upper()[:2])

    # If selected_books is not empty, filter by it
    if selected_books and book_abbrev not in selected_books:
        logger.debug(f"Skipping alert for {book_abbrev} - not in selected books: {selected_books}")
        return False

    # Get repost info BEFORE checking duplicate (need previous data)
    repost_info = get_repost_info(opp)

    if is_duplicate_alert(opp):
        return False

    # Enrich DK alerts with dummy legs + SGP links (only after passing dedup)
    if props and best_book == 'draftkings':
        enrich_dk_opportunity(opp, props)

    try:
        message = format_alert_message(opp, repost_info)
        await app.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode=ParseMode.HTML,
            link_preview_options=NO_PREVIEW
        )

        record_sent_alert(opp)
        is_repost = " (REPOST)" if repost_info else ""
        logger.info(f"Sent alert{is_repost}: {opp['player']} {opp['market']} ({opp['tier']})")
        return True
    except Exception as e:
        logger.error(f"Failed to send alert: {e}")
        return False


# =============================================================================
# TELEGRAM BOT HANDLERS
# =============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - matches production welcome message."""
    interval = SCAN_INTERVAL_SECONDS
    state_upper = current_state.upper()

    welcome_msg = f"""
🏀 <b>OddsBlaze NBA Scanner Bot</b>

Scanning NBA player props for +EV betting opportunities!

<b>Commands:</b>
/scan - Run manual scan (shows tier selection)
/status - Bot status and stats
/books - View sportsbooks
/pause - Pause automatic alerts
/resume - Resume automatic alerts

<b>Quick Scans:</b>
/dk /fd /mg /cz /br /fn /bp

<b>Alert Tiers:</b>
🔥 FIRE - High confidence (Kelly ≥0.3, Cov ≥8)
🎯 VALUE_LONGSHOT - Long odds value (+500, Kelly ≥0.15)
⚡ OUTLIER - Market outlier (35%+ vs next)

<b>Current State:</b> {state_upper}
<b>Scan Interval:</b> {interval}s
<b>Sportsbooks:</b> {len(SPORTSBOOKS)}

<b>Data Source:</b> OddsBlaze API
"""
    await update.message.reply_text(welcome_msg, parse_mode=ParseMode.HTML)


async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /scan command - show tier selection buttons."""
    keyboard = [
        [
            InlineKeyboardButton("🔥", callback_data="scantier_FIRE"),
            InlineKeyboardButton("🎯", callback_data="scantier_VALUE_LONGSHOT"),
            InlineKeyboardButton("⚡", callback_data="scantier_OUTLIER"),
            InlineKeyboardButton("📊 All", callback_data="scantier_ALL"),
            InlineKeyboardButton("🔒", callback_data="scantier_CUSTOM"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🔍 <b>Manual Scan</b> ({current_state.upper()})\n"
        f"📚 {len(SPORTSBOOKS)} sportsbooks\n\n"
        f"Select tier filter:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def scan_tier_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle scan tier selection callback."""
    query = update.callback_query
    await query.answer()

    tier = query.data.split("_")[1]
    chat_id = update.effective_chat.id

    if tier == "CUSTOM":
        keyboard = [
            [
                InlineKeyboardButton("5%", callback_data="scancustomev_5"),
                InlineKeyboardButton("10%", callback_data="scancustomev_10"),
                InlineKeyboardButton("15%", callback_data="scancustomev_15"),
                InlineKeyboardButton("20%", callback_data="scancustomev_20"),
                InlineKeyboardButton("25%", callback_data="scancustomev_25"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"🔍 <b>Manual Scan</b> ({current_state.upper()})\n\n"
            f"🔒 Custom - Select min EV%:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        return

    await run_manual_scan(query, context, tier, chat_id)


async def scan_custom_ev_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom EV selection."""
    query = update.callback_query
    await query.answer()

    min_ev = int(query.data.split("_")[1])

    keyboard = [
        [
            InlineKeyboardButton(">0", callback_data=f"scancustomkelly_{min_ev}_0.001"),
            InlineKeyboardButton("0.05", callback_data=f"scancustomkelly_{min_ev}_0.05"),
            InlineKeyboardButton("0.15", callback_data=f"scancustomkelly_{min_ev}_0.15"),
            InlineKeyboardButton("0.3", callback_data=f"scancustomkelly_{min_ev}_0.3"),
        ],
        [
            InlineKeyboardButton("0.5", callback_data=f"scancustomkelly_{min_ev}_0.5"),
            InlineKeyboardButton("0.75", callback_data=f"scancustomkelly_{min_ev}_0.75"),
            InlineKeyboardButton("1.0", callback_data=f"scancustomkelly_{min_ev}_1.0"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"🔍 <b>Manual Scan</b>\n\n"
        f"🔒 Custom - EV≥{min_ev}%\n"
        f"Select min Kelly:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def scan_custom_kelly_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom Kelly selection."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    min_ev = int(parts[1])
    min_kelly = float(parts[2])

    keyboard = [
        [
            InlineKeyboardButton("+100", callback_data=f"scancustomodds_{min_ev}_{min_kelly}_100"),
            InlineKeyboardButton("+200", callback_data=f"scancustomodds_{min_ev}_{min_kelly}_200"),
            InlineKeyboardButton("+300", callback_data=f"scancustomodds_{min_ev}_{min_kelly}_300"),
            InlineKeyboardButton("+500", callback_data=f"scancustomodds_{min_ev}_{min_kelly}_500"),
        ],
        [
            InlineKeyboardButton("+1000", callback_data=f"scancustomodds_{min_ev}_{min_kelly}_1000"),
            InlineKeyboardButton("+1500", callback_data=f"scancustomodds_{min_ev}_{min_kelly}_1500"),
            InlineKeyboardButton("+2000", callback_data=f"scancustomodds_{min_ev}_{min_kelly}_2000"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"🔍 <b>Manual Scan</b>\n\n"
        f"🔒 Custom Filter\n"
        f"✅ EV ≥ {min_ev}%\n"
        f"✅ Kelly ≥ {min_kelly}\n\n"
        f"Select minimum odds:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def scan_custom_odds_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom odds selection - run the scan."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    min_ev = int(parts[1])
    min_kelly = float(parts[2])
    min_odds = int(parts[3])

    chat_id = update.effective_chat.id

    await run_manual_scan(query, context, "CUSTOM", chat_id, min_ev, min_kelly, min_odds)


async def run_manual_scan(query, context, tier: str, chat_id: int, min_ev: float = None, min_kelly: float = None, min_odds: int = None):
    """Execute manual scan with selected tier/custom filter."""
    tier_labels = {'FIRE': '🔥 Fire', 'VALUE_LONGSHOT': '🎯 Longshot', 'OUTLIER': '⚡ Outlier', 'ALL': '📊 All', 'CUSTOM': '🔒 Custom'}
    tier_label = tier_labels.get(tier, tier)

    if tier == "CUSTOM":
        filter_text = f"🔒 EV≥{min_ev}%, Kelly≥{min_kelly}, Odds≥+{min_odds}"
    else:
        filter_text = f"Tier: {tier_label}"

    await query.edit_message_text(
        f"🔄 Scanning NBA odds...\n"
        f"📚 {len(SPORTSBOOKS)} sportsbooks\n"
        f"📋 {filter_text}",
        parse_mode=ParseMode.HTML
    )

    try:
        all_odds = fetch_all_odds()
        props = aggregate_player_props(all_odds)
        all_opportunities = scan_for_value(props, min_ev=0, min_odds=0)

        if not all_opportunities:
            await context.bot.send_message(chat_id=chat_id, text="No opportunities found. Markets may be closed.")
            return

        # Filter by tier
        if tier == "CUSTOM":
            opportunities = [o for o in all_opportunities
                          if o['ev_pct'] >= min_ev and o['kelly'] >= min_kelly and o['best_odds'] >= min_odds]
        elif tier == "ALL":
            opportunities = all_opportunities
        else:
            opportunities = [o for o in all_opportunities if o['tier'] == tier]

        if not opportunities:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"No {tier_label} alerts found. Total opportunities: {len(all_opportunities)}",
                parse_mode=ParseMode.HTML
            )
            return

        total_alerts = len(opportunities)

        summary = f"📊 <b>Scan Complete - {tier_label}</b>\n"
        if tier == "CUSTOM":
            summary += f"Filter: EV≥{min_ev}%, Kelly≥{min_kelly}, Odds≥+{min_odds}\n"
        summary += f"Found {total_alerts} alerts"
        await context.bot.send_message(chat_id=chat_id, text=summary, parse_mode=ParseMode.HTML)

        # Send first 5 alerts (with deduplication)
        BATCH_SIZE = 5
        sent_count = 0

        for opp in opportunities[:BATCH_SIZE]:
            repost_info = get_repost_info(opp)
            if is_duplicate_alert(opp):
                continue
            # Enrich DK alerts with dummy legs
            if opp.get('best_book') == 'draftkings':
                enrich_dk_opportunity(opp, props)
            msg = format_alert_message(opp, repost_info)
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML, link_preview_options=NO_PREVIEW)
            record_sent_alert(opp)
            sent_count += 1
            await asyncio.sleep(0.3)

        # Show More button if needed
        remaining = total_alerts - BATCH_SIZE
        if remaining > 0:
            pending_alerts[chat_id] = {
                'alerts': opportunities,
                'offset': sent_count,
                'props': props,  # Store props for dummy leg enrichment in Show More
            }

            keyboard = [[
                InlineKeyboardButton(
                    f"📋 Show More ({remaining} remaining)",
                    callback_data="show_more"
                )
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(
                chat_id=chat_id,
                text=f"📊 Showing {sent_count}/{total_alerts} alerts",
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )

    except Exception as e:
        logger.error(f"Error in manual scan: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Scan error: {str(e)}")


async def show_more_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'Show More' button callback."""
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id

    if chat_id not in pending_alerts:
        await query.edit_message_text("⚠️ No more alerts available. Run /scan again.")
        return

    data = pending_alerts[chat_id]
    alerts = data['alerts']
    offset = data['offset']
    stored_props = data.get('props')  # May be None for older entries
    total_alerts = len(alerts)

    await query.edit_message_text(
        f"📊 Showed {offset}/{total_alerts} alerts",
        parse_mode=ParseMode.HTML
    )

    BATCH_SIZE = 5
    sent_count = 0
    checked_count = 0

    for i in range(offset, min(offset + BATCH_SIZE + 10, total_alerts)):  # Check extra to find non-duplicates
        if sent_count >= BATCH_SIZE:
            break
        opp = alerts[i]
        checked_count += 1
        repost_info = get_repost_info(opp)
        if is_duplicate_alert(opp):
            continue
        # Enrich DK alerts with dummy legs
        if stored_props and opp.get('best_book') == 'draftkings':
            enrich_dk_opportunity(opp, stored_props)
        msg = format_alert_message(opp, repost_info)
        await context.bot.send_message(
            chat_id=chat_id,
            text=msg,
            parse_mode=ParseMode.HTML,
            link_preview_options=NO_PREVIEW
        )
        record_sent_alert(opp)
        sent_count += 1
        await asyncio.sleep(0.3)

    new_offset = offset + checked_count
    remaining = total_alerts - new_offset

    if remaining > 0:
        pending_alerts[chat_id]['offset'] = new_offset

        keyboard = [[
            InlineKeyboardButton(
                f"📋 Show More ({remaining} remaining)",
                callback_data="show_more"
            )
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"📊 Showing {new_offset}/{total_alerts} alerts",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    else:
        del pending_alerts[chat_id]
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ All {total_alerts} alerts shown",
            parse_mode=ParseMode.HTML
        )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command."""
    now_et = datetime.now(ET)
    tier_status = " ".join([
        f"🔥" if 'FIRE' in active_tiers else "○",
        f"🎯" if 'VALUE_LONGSHOT' in active_tiers else "○",
        f"⚡" if 'OUTLIER' in active_tiers else "○",
    ])

    # Build selected books display
    if selected_books:
        books_display = ', '.join(selected_books)
    else:
        books_display = f"All ({', '.join(RETAIL_BOOKS)})"

    msg = f"📊 <b>OddsBlaze Scanner Status</b>\n\n"
    msg += f"<b>Auto-scan:</b> {'✅ ON' if auto_scan_enabled and not is_paused else '❌ OFF'}\n"
    msg += f"<b>Paused:</b> {'Yes' if is_paused else 'No'}\n"
    msg += f"<b>Interval:</b> {scan_interval}s\n"
    msg += f"<b>Active tiers:</b> {tier_status}\n"
    msg += f"<b>Selected books:</b> {books_display}\n"
    msg += f"<b>Alerts sent:</b> {len(sent_alerts)}\n"
    msg += f"<b>State:</b> {current_state.upper()}\n"
    msg += f"<b>Time (ET):</b> {now_et.strftime('%I:%M %p')}\n"

    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


async def books_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /books command."""
    msg = f"📚 <b>Sportsbooks ({len(SPORTSBOOKS)})</b>\n\n"

    for book in SPORTSBOOKS:
        config = BOOK_CONFIG.get(book, {})
        abbrev = config.get('abbrev', book[:2].upper())
        name = config.get('name', book)
        sharp = " (Sharp)" if book in SHARP_BOOKS else ""
        msg += f"• <b>{abbrev}</b> - {name}{sharp}\n"

    msg += f"\n<b>State:</b> {current_state.upper()}"
    msg += f"\n<b>Supported States:</b> {', '.join([s.upper() for s in SUPPORTED_STATES])}"

    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /pause command."""
    global is_paused
    is_paused = True
    await update.message.reply_text("⏸️ Automatic alerts paused. Use /resume to restart.")
    logger.info("Automatic alerts paused by user")


async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /resume command - Step 1: Show tier selection."""
    # Show current settings
    if use_custom_filter:
        current_label = f"Custom (EV≥{custom_filter['min_ev']}%, Kelly≥{custom_filter['min_kelly']}, Odds≥+{custom_filter['min_odds']})"
    elif active_tiers == {'FIRE', 'VALUE_LONGSHOT', 'OUTLIER'}:
        current_label = "All"
    else:
        tier_emojis = {'FIRE': '🔥', 'VALUE_LONGSHOT': '🎯', 'OUTLIER': '⚡'}
        current_label = ', '.join(tier_emojis.get(t, t) for t in active_tiers)

    keyboard = [
        [
            InlineKeyboardButton("🔥 Fire", callback_data="resumetier_FIRE"),
            InlineKeyboardButton("🎯 Longshot", callback_data="resumetier_VALUE_LONGSHOT"),
            InlineKeyboardButton("⚡ Outlier", callback_data="resumetier_OUTLIER"),
        ],
        [
            InlineKeyboardButton("📊 All", callback_data="resumetier_ALL"),
            InlineKeyboardButton("🔒 Custom", callback_data="resumetier_CUSTOM"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"▶️ <b>Resume Alerts</b>\n\n"
        f"Current: {current_label}\n"
        f"Interval: {scan_interval}s\n\n"
        f"Select tier filter:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def resume_tier_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle resume tier selection - Step 2: Show interval or custom filter."""
    global active_tiers, use_custom_filter
    query = update.callback_query
    await query.answer()

    tier = query.data.split("_")[1]

    # If CUSTOM selected, show EV threshold options first
    if tier == "CUSTOM":
        keyboard = [
            [
                InlineKeyboardButton("EV≥5%", callback_data="customev_5"),
                InlineKeyboardButton("EV≥10%", callback_data="customev_10"),
                InlineKeyboardButton("EV≥15%", callback_data="customev_15"),
            ],
            [
                InlineKeyboardButton("EV≥20%", callback_data="customev_20"),
                InlineKeyboardButton("EV≥25%", callback_data="customev_25"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🔒 <b>Custom Filter - Step 1</b>\n\nSelect minimum EV%:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        return

    # Set tier(s)
    use_custom_filter = False
    if tier == "ALL":
        active_tiers = {'FIRE', 'VALUE_LONGSHOT', 'OUTLIER'}
        tier_label = "All tiers"
    else:
        active_tiers = {tier}
        tier_label = {'FIRE': '🔥 Fire', 'VALUE_LONGSHOT': '🎯 Longshot', 'OUTLIER': '⚡ Outlier'}.get(tier, tier)

    # Show interval selection
    keyboard = [[
        InlineKeyboardButton("4s", callback_data="interval_4"),
        InlineKeyboardButton("10s", callback_data="interval_10"),
        InlineKeyboardButton("20s", callback_data="interval_20"),
        InlineKeyboardButton("30s", callback_data="interval_30"),
        InlineKeyboardButton("1m", callback_data="interval_60"),
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"✅ {tier_label} selected\n\n"
        f"⏰ Select scan interval (current: {scan_interval}s):",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )
    logger.info(f"Alert tier set to: {tier}")


async def custom_ev_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom EV selection - Step 2: Show Kelly options."""
    query = update.callback_query
    await query.answer()

    min_ev = int(query.data.split("_")[1])
    custom_filter['min_ev'] = min_ev

    keyboard = [
        [
            InlineKeyboardButton("Kelly>0", callback_data=f"customkelly_{min_ev}_0.001"),
            InlineKeyboardButton("Kelly≥0.05", callback_data=f"customkelly_{min_ev}_0.05"),
            InlineKeyboardButton("Kelly≥0.15", callback_data=f"customkelly_{min_ev}_0.15"),
            InlineKeyboardButton("Kelly≥0.3", callback_data=f"customkelly_{min_ev}_0.3"),
        ],
        [
            InlineKeyboardButton("Kelly≥0.5", callback_data=f"customkelly_{min_ev}_0.5"),
            InlineKeyboardButton("Kelly≥0.75", callback_data=f"customkelly_{min_ev}_0.75"),
            InlineKeyboardButton("Kelly≥1.0", callback_data=f"customkelly_{min_ev}_1.0"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"🔒 <b>Custom Filter - Step 2</b>\n\n"
        f"✅ EV ≥ {min_ev}%\n\n"
        f"Select minimum Kelly:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def custom_kelly_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom Kelly selection - Step 3: Show min odds options."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    min_ev = int(parts[1])
    min_kelly = float(parts[2])
    custom_filter['min_ev'] = min_ev
    custom_filter['min_kelly'] = min_kelly

    keyboard = [
        [
            InlineKeyboardButton("+100", callback_data=f"customodds_{min_ev}_{min_kelly}_100"),
            InlineKeyboardButton("+200", callback_data=f"customodds_{min_ev}_{min_kelly}_200"),
            InlineKeyboardButton("+300", callback_data=f"customodds_{min_ev}_{min_kelly}_300"),
            InlineKeyboardButton("+500", callback_data=f"customodds_{min_ev}_{min_kelly}_500"),
        ],
        [
            InlineKeyboardButton("+1000", callback_data=f"customodds_{min_ev}_{min_kelly}_1000"),
            InlineKeyboardButton("+1500", callback_data=f"customodds_{min_ev}_{min_kelly}_1500"),
            InlineKeyboardButton("+2000", callback_data=f"customodds_{min_ev}_{min_kelly}_2000"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"🔒 <b>Custom Filter - Step 3</b>\n\n"
        f"✅ EV ≥ {min_ev}%\n"
        f"✅ Kelly ≥ {min_kelly}\n\n"
        f"Select minimum odds:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def custom_odds_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom odds selection - Step 4: Show interval options."""
    global use_custom_filter
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    min_ev = int(parts[1])
    min_kelly = float(parts[2])
    min_odds = int(parts[3])

    custom_filter['min_ev'] = min_ev
    custom_filter['min_kelly'] = min_kelly
    custom_filter['min_odds'] = min_odds
    use_custom_filter = True

    # Show interval selection
    keyboard = [[
        InlineKeyboardButton("4s", callback_data="interval_4"),
        InlineKeyboardButton("10s", callback_data="interval_10"),
        InlineKeyboardButton("20s", callback_data="interval_20"),
        InlineKeyboardButton("30s", callback_data="interval_30"),
        InlineKeyboardButton("1m", callback_data="interval_60"),
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"✅ Custom filter set:\n"
        f"   EV ≥ {min_ev}%\n"
        f"   Kelly ≥ {min_kelly}\n"
        f"   Odds ≥ +{min_odds}\n\n"
        f"⏰ Select scan interval (current: {scan_interval}s):",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )
    logger.info(f"Custom filter set: EV>={min_ev}%, Kelly>={min_kelly}, Odds>=+{min_odds}")


async def interval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle interval selection - Step 5: Show book selection."""
    global scan_interval
    query = update.callback_query
    await query.answer()

    interval_seconds = int(query.data.split("_")[1])
    scan_interval = interval_seconds

    interval_label = f"{interval_seconds}s" if interval_seconds < 60 else f"{interval_seconds // 60}m"

    if use_custom_filter:
        filter_label = f"Custom (EV≥{custom_filter['min_ev']}%, Kelly≥{custom_filter['min_kelly']}, Odds≥+{custom_filter['min_odds']})"
    else:
        tier_emojis = {'FIRE': '🔥', 'VALUE_LONGSHOT': '🎯', 'OUTLIER': '⚡'}
        filter_label = ', '.join(tier_emojis.get(t, t) for t in active_tiers)

    # Build book selection buttons
    is_default_all = not selected_books  # Empty means all
    keyboard = []
    row = []
    for book_abbrev in RETAIL_BOOKS:
        is_selected = book_abbrev in selected_books or is_default_all
        checkmark = "✅ " if is_selected else ""
        btn_text = f"{checkmark}{book_abbrev}"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"togglebook_{book_abbrev}"))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    # Add "All Books" and "Done" buttons
    keyboard.append([
        InlineKeyboardButton("📚 All Books", callback_data="togglebook_ALL"),
        InlineKeyboardButton("✅ Done", callback_data="books_done"),
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"✅ Interval: {interval_label}\n"
        f"📋 Filter: {filter_label}\n\n"
        f"📖 <b>Select sportsbooks to send alerts for:</b>\n"
        f"<i>Tap to toggle, then press Done</i>",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )
    logger.info(f"Showing book selection (interval: {interval_label})")


async def toggle_book_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle book toggle button callback."""
    global selected_books
    query = update.callback_query
    await query.answer()

    book = query.data.split("_")[1]

    # Check if this is the default "all" state (empty list)
    is_default_all = not selected_books

    if book == "ALL":
        # Toggle all: if currently all selected, deselect all; otherwise select all
        if is_default_all or set(selected_books) == set(RETAIL_BOOKS):
            # Deselect all
            selected_books = []
        else:
            # Select all
            selected_books = RETAIL_BOOKS.copy()
    else:
        # Toggle individual book
        if is_default_all:
            # First click when default all - start fresh with just this book
            selected_books = [book]
        elif book in selected_books:
            selected_books.remove(book)
        else:
            selected_books.append(book)

    # Rebuild buttons
    is_default_all = not selected_books
    keyboard = []
    row = []
    for book_abbrev in RETAIL_BOOKS:
        is_selected = book_abbrev in selected_books or is_default_all
        checkmark = "✅ " if is_selected else ""
        btn_text = f"{checkmark}{book_abbrev}"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"togglebook_{book_abbrev}"))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append([
        InlineKeyboardButton("📚 All Books", callback_data="togglebook_ALL"),
        InlineKeyboardButton("✅ Done", callback_data="books_done"),
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Build filter label
    if use_custom_filter:
        filter_label = f"Custom (EV≥{custom_filter['min_ev']}%, Kelly≥{custom_filter['min_kelly']}, Odds≥+{custom_filter['min_odds']})"
    else:
        tier_emojis = {'FIRE': '🔥', 'VALUE_LONGSHOT': '🎯', 'OUTLIER': '⚡'}
        filter_label = ', '.join(tier_emojis.get(t, t) for t in active_tiers)

    interval_label = f"{scan_interval}s" if scan_interval < 60 else f"{scan_interval // 60}m"
    selected_display = ', '.join(selected_books) if selected_books else "All books"

    await query.edit_message_text(
        f"✅ Interval: {interval_label}\n"
        f"📋 Filter: {filter_label}\n\n"
        f"📖 <b>Select sportsbooks to send alerts for:</b>\n"
        f"<i>Selected: {selected_display}</i>",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def books_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'Done' button for book selection - Final step: Resume alerts."""
    global is_paused, force_next_scan
    query = update.callback_query
    await query.answer()

    # Unpause and force immediate scan
    is_paused = False
    force_next_scan = True

    # Build filter label
    if use_custom_filter:
        filter_label = f"Custom (EV≥{custom_filter['min_ev']}%, Kelly≥{custom_filter['min_kelly']}, Odds≥+{custom_filter['min_odds']})"
    else:
        tier_emojis = {'FIRE': '🔥', 'VALUE_LONGSHOT': '🎯', 'OUTLIER': '⚡'}
        filter_label = ', '.join(tier_emojis.get(t, t) for t in active_tiers)

    interval_label = f"{scan_interval}s" if scan_interval < 60 else f"{scan_interval // 60}m"

    # Build books display
    if selected_books:
        books_display = ', '.join(selected_books)
    else:
        books_display = f"All ({', '.join(RETAIL_BOOKS)})"

    await query.edit_message_text(
        f"▶️ <b>Alerts Resumed!</b>\n\n"
        f"📋 Filter: <b>{filter_label}</b>\n"
        f"⏰ Interval: <b>{interval_label}</b>\n"
        f"📖 Books: <b>{books_display}</b>\n\n"
        f"Auto-scanning is now active.",
        parse_mode=ParseMode.HTML
    )
    logger.info(f"Alerts resumed with interval: {interval_label}, books: {books_display}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_text = """
🏀 <b>OddsBlaze Scanner Commands</b>

<b>Scanning:</b>
/scan - Manual scan with tier selection
/dk /fd /mg /cz /br /fn /bp - Per-book scans

<b>Settings:</b>
/status - Bot status
/books - View sportsbooks
/pause - Pause auto-alerts
/resume - Resume auto-alerts

<b>Tier Legend:</b>
🔥 FIRE - High Kelly (30%+), 8+ books
🎯 VALUE - Longshot value (+500 odds)
⚡ OUTLIER - Significantly better than market

<b>Data Source:</b> OddsBlaze API
"""
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)


# Per-book scan commands
async def book_scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE, book_abbrev: str, book_name: str):
    """Generic handler for per-book scan commands."""
    keyboard = [
        [
            InlineKeyboardButton("🔥", callback_data=f"booktier_{book_abbrev}_FIRE"),
            InlineKeyboardButton("🎯", callback_data=f"booktier_{book_abbrev}_VALUE_LONGSHOT"),
            InlineKeyboardButton("⚡", callback_data=f"booktier_{book_abbrev}_OUTLIER"),
            InlineKeyboardButton("📊 All", callback_data=f"booktier_{book_abbrev}_ALL"),
            InlineKeyboardButton("🔒", callback_data=f"booktier_{book_abbrev}_CUSTOM"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"📚 <b>{book_name} Scan</b>\n\n"
        f"Select tier filter:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def book_tier_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle book tier selection callback."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    book_abbrev = parts[1]
    tier = parts[2]

    book_name = next((v['name'] for k, v in BOOK_CONFIG.items() if v['abbrev'] == book_abbrev), book_abbrev)
    chat_id = update.effective_chat.id

    # If CUSTOM selected, show EV threshold options
    if tier == "CUSTOM":
        keyboard = [
            [
                InlineKeyboardButton("5%", callback_data=f"bookcustomev_{book_abbrev}_5"),
                InlineKeyboardButton("10%", callback_data=f"bookcustomev_{book_abbrev}_10"),
                InlineKeyboardButton("15%", callback_data=f"bookcustomev_{book_abbrev}_15"),
                InlineKeyboardButton("20%", callback_data=f"bookcustomev_{book_abbrev}_20"),
                InlineKeyboardButton("25%", callback_data=f"bookcustomev_{book_abbrev}_25"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"📚 <b>{book_name} Scan</b>\n\n"
            f"🔒 Custom - Select min EV%:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        return

    await run_book_scan(query, context, book_abbrev, book_name, tier, chat_id)


async def book_custom_ev_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle book custom EV selection - show Kelly options."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    book_abbrev = parts[1]
    min_ev = int(parts[2])
    book_name = next((v['name'] for k, v in BOOK_CONFIG.items() if v['abbrev'] == book_abbrev), book_abbrev)

    keyboard = [
        [
            InlineKeyboardButton(">0", callback_data=f"bookcustomkelly_{book_abbrev}_{min_ev}_0.001"),
            InlineKeyboardButton("0.05", callback_data=f"bookcustomkelly_{book_abbrev}_{min_ev}_0.05"),
            InlineKeyboardButton("0.15", callback_data=f"bookcustomkelly_{book_abbrev}_{min_ev}_0.15"),
            InlineKeyboardButton("0.3", callback_data=f"bookcustomkelly_{book_abbrev}_{min_ev}_0.3"),
        ],
        [
            InlineKeyboardButton("0.5", callback_data=f"bookcustomkelly_{book_abbrev}_{min_ev}_0.5"),
            InlineKeyboardButton("0.75", callback_data=f"bookcustomkelly_{book_abbrev}_{min_ev}_0.75"),
            InlineKeyboardButton("1.0", callback_data=f"bookcustomkelly_{book_abbrev}_{min_ev}_1.0"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"📚 <b>{book_name} Scan</b>\n\n"
        f"🔒 Custom - EV≥{min_ev}%\n"
        f"Select min Kelly:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def book_custom_kelly_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle book custom Kelly selection - show odds options."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    book_abbrev = parts[1]
    min_ev = int(parts[2])
    min_kelly = float(parts[3])
    book_name = next((v['name'] for k, v in BOOK_CONFIG.items() if v['abbrev'] == book_abbrev), book_abbrev)

    keyboard = [
        [
            InlineKeyboardButton("+100", callback_data=f"bookcustomodds_{book_abbrev}_{min_ev}_{min_kelly}_100"),
            InlineKeyboardButton("+200", callback_data=f"bookcustomodds_{book_abbrev}_{min_ev}_{min_kelly}_200"),
            InlineKeyboardButton("+300", callback_data=f"bookcustomodds_{book_abbrev}_{min_ev}_{min_kelly}_300"),
            InlineKeyboardButton("+500", callback_data=f"bookcustomodds_{book_abbrev}_{min_ev}_{min_kelly}_500"),
        ],
        [
            InlineKeyboardButton("+1000", callback_data=f"bookcustomodds_{book_abbrev}_{min_ev}_{min_kelly}_1000"),
            InlineKeyboardButton("+1500", callback_data=f"bookcustomodds_{book_abbrev}_{min_ev}_{min_kelly}_1500"),
            InlineKeyboardButton("+2000", callback_data=f"bookcustomodds_{book_abbrev}_{min_ev}_{min_kelly}_2000"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"📚 <b>{book_name} Scan</b>\n\n"
        f"🔒 Custom Filter\n"
        f"✅ EV ≥ {min_ev}%\n"
        f"✅ Kelly ≥ {min_kelly}\n\n"
        f"Select minimum odds:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def book_custom_odds_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle book custom odds selection - run the book scan."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    book_abbrev = parts[1]
    min_ev = int(parts[2])
    min_kelly = float(parts[3])
    min_odds = int(parts[4])

    book_name = next((v['name'] for k, v in BOOK_CONFIG.items() if v['abbrev'] == book_abbrev), book_abbrev)
    chat_id = update.effective_chat.id

    await run_book_scan(query, context, book_abbrev, book_name, "CUSTOM", chat_id, min_ev, min_kelly, min_odds)


async def run_book_scan(query, context, book_abbrev: str, book_name: str, tier: str, chat_id: int, min_ev: float = None, min_kelly: float = None, min_odds: int = None):
    """Execute book scan with selected tier or custom filter."""
    tier_labels = {'FIRE': '🔥', 'VALUE_LONGSHOT': '🎯', 'OUTLIER': '⚡', 'ALL': 'All', 'CUSTOM': '🔒 Custom'}
    tier_label = tier_labels.get(tier, tier)

    if tier == "CUSTOM":
        filter_text = f"🔒 EV≥{min_ev}%, Kelly≥{min_kelly}, Odds≥+{min_odds}"
    else:
        filter_text = f"Tier: {tier_label}"

    await query.edit_message_text(
        f"🔄 Scanning <b>{book_name}</b>...\n"
        f"📋 {filter_text}",
        parse_mode=ParseMode.HTML
    )

    try:
        all_odds = fetch_all_odds()
        props = aggregate_player_props(all_odds)
        all_opportunities = scan_for_value(props, min_ev=0, min_odds=0)

        if not all_opportunities:
            await context.bot.send_message(chat_id=chat_id, text="No opportunities found.")
            return

        # Filter by tier
        if tier == "CUSTOM":
            opportunities = [o for o in all_opportunities
                           if o['ev_pct'] >= min_ev and o['kelly'] >= min_kelly and o['best_odds'] >= min_odds]
        elif tier == "ALL":
            opportunities = all_opportunities
        else:
            opportunities = [o for o in all_opportunities if o['tier'] == tier]

        # Filter to only bets where specified book has best odds
        book_opportunities = [o for o in opportunities if o['best_book'].lower() == book_abbrev.lower() or
                            BOOK_CONFIG.get(o['best_book'], {}).get('abbrev', '').upper() == book_abbrev.upper()]

        if not book_opportunities:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"No {tier_label} alerts with best odds on {book_name}.\nTotal: {len(all_opportunities)}",
                parse_mode=ParseMode.HTML
            )
            return

        total = len(book_opportunities)
        summary = f"📊 <b>{book_name} - {tier_label}</b>\n"
        if tier == "CUSTOM":
            summary += f"Filter: EV≥{min_ev}%, Kelly≥{min_kelly}, Odds≥+{min_odds}\n"
        summary += f"Found {total} alerts"
        await context.bot.send_message(chat_id=chat_id, text=summary, parse_mode=ParseMode.HTML)

        # Manual book scans ignore deduplication - send all matching opportunities
        sent_count = 0
        for opp in book_opportunities:
            if sent_count >= 15:  # Limit to 15 for manual scans
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"<i>... and {total - sent_count} more. Use filters to narrow down.</i>",
                    parse_mode=ParseMode.HTML
                )
                break
            # Enrich DK alerts with dummy legs
            if opp.get('best_book') == 'draftkings':
                enrich_dk_opportunity(opp, props)
            msg = format_alert_message(opp, repost_info=None)  # No repost info for manual scans
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML, link_preview_options=NO_PREVIEW)
            sent_count += 1
            await asyncio.sleep(0.3)

        logger.info(f"Manual {book_name} scan: sent {sent_count}/{total} alerts")

    except Exception as e:
        logger.error(f"Error in {book_name} scan: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Scan error: {str(e)}")


# Individual book commands
async def dk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await book_scan_command(update, context, 'DK', 'DraftKings')

async def fd_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await book_scan_command(update, context, 'FD', 'FanDuel')

async def mg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await book_scan_command(update, context, 'MG', 'BetMGM')

async def cz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await book_scan_command(update, context, 'CZ', 'Caesars')

async def br_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await book_scan_command(update, context, 'BR', 'BetRivers')

async def fn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await book_scan_command(update, context, 'FN', 'Fanatics')

async def bp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await book_scan_command(update, context, 'BP', 'BetParx')

async def fl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await book_scan_command(update, context, 'FL', 'Fliff')

async def ts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await book_scan_command(update, context, 'TS', 'theScore')

async def b3_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await book_scan_command(update, context, 'B3', 'bet365')

async def bb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await book_scan_command(update, context, 'BB', 'Bally Bet')

async def hr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await book_scan_command(update, context, 'HR', 'Hard Rock')


# =============================================================================
# AUTO SCAN LOOP
# =============================================================================

def check_midnight_reset():
    """Check if we've crossed midnight EST and reset sent_alerts if so."""
    global sent_alerts, last_reset_date

    now_et = datetime.now(ET)
    today_str = now_et.strftime('%Y-%m-%d')

    if last_reset_date is None:
        # First run - initialize without clearing (preserve any alerts from same day)
        last_reset_date = today_str
        logger.info(f"Initialized reset date: {today_str}")
        return False

    if today_str != last_reset_date:
        # New day - clear all sent alerts
        alert_count = len(sent_alerts)
        sent_alerts = {}
        last_reset_date = today_str
        logger.info(f"🌅 Midnight reset: Cleared {alert_count} sent alerts for new day ({today_str})")
        return True

    return False


async def auto_scan_loop(app: Application):
    """Background task for automatic scanning."""
    global is_paused
    logger.info("Starting auto-scan loop...")

    # Initialize midnight reset tracking
    check_midnight_reset()

    # Start paused and prompt for setup
    is_paused = True

    # Send startup message with setup buttons (like /resume)
    try:
        keyboard = [
            [
                InlineKeyboardButton("🔥 Fire", callback_data="resumetier_FIRE"),
                InlineKeyboardButton("🎯 Longshot", callback_data="resumetier_VALUE_LONGSHOT"),
                InlineKeyboardButton("⚡ Outlier", callback_data="resumetier_OUTLIER"),
            ],
            [
                InlineKeyboardButton("📊 All", callback_data="resumetier_ALL"),
                InlineKeyboardButton("🔒 Custom", callback_data="resumetier_CUSTOM"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await app.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"🚀 <b>OddsBlaze Scanner Started!</b>\n\n"
                 f"📊 {len(SPORTSBOOKS)} sportsbooks available\n\n"
                 f"<b>Configure your alerts:</b>\n"
                 f"Select tier filter to begin:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        logger.info("Sent startup setup prompt - waiting for user configuration")
    except Exception as e:
        logger.error(f"Failed to send startup message: {e}")

    while True:
        try:
            global force_next_scan

            # Check for midnight reset (clears sent_alerts at midnight EST)
            check_midnight_reset()

            # Check if we should scan: either during active hours OR force_next_scan is True
            should_scan = auto_scan_enabled and not is_paused and (is_active_hours() or force_next_scan)

            if should_scan:
                if force_next_scan:
                    logger.info(f"Running forced scan after /resume (bypassing active hours)...")
                    force_next_scan = False  # Reset after using
                else:
                    logger.info(f"Running auto-scan (interval: {scan_interval}s)...")

                all_odds = fetch_all_odds()
                props = aggregate_player_props(all_odds)
                opportunities = scan_for_value(props, min_ev=0, min_odds=0)

                # Apply filter based on settings
                if use_custom_filter:
                    # Apply custom filter
                    filtered_opps = [
                        o for o in opportunities
                        if o['ev_pct'] >= custom_filter['min_ev']
                        and o['kelly'] >= custom_filter['min_kelly']
                        and o['best_odds'] >= custom_filter['min_odds']
                    ]
                    logger.info(f"Found {len(filtered_opps)} opportunities (custom filter: EV>={custom_filter['min_ev']}%, Kelly>={custom_filter['min_kelly']}, Odds>=+{custom_filter['min_odds']})")
                else:
                    # Filter by active tiers
                    filtered_opps = [o for o in opportunities if o['tier'] in active_tiers]
                    logger.info(f"Found {len(filtered_opps)} opportunities (filtered by tiers: {active_tiers})")

                alerts_sent = 0
                duplicates_skipped = 0
                for opp in filtered_opps:  # Check ALL opportunities
                    if alerts_sent >= 10:  # Stop after SENDING 10
                        break
                    if await send_alert(app, opp, props=props):
                        alerts_sent += 1
                        await asyncio.sleep(1)
                    else:
                        duplicates_skipped += 1

                if alerts_sent > 0 or duplicates_skipped > 0:
                    logger.info(f"Sent {alerts_sent} alerts, skipped {duplicates_skipped} duplicates")

            await asyncio.sleep(scan_interval)

        except Exception as e:
            logger.error(f"Auto-scan error: {e}")
            await asyncio.sleep(60)


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Start the bot."""
    logger.info("Starting OddsBlaze Scanner Bot...")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("books", books_command))
    app.add_handler(CommandHandler("pause", pause_command))
    app.add_handler(CommandHandler("resume", resume_command))

    # Per-book commands
    app.add_handler(CommandHandler("dk", dk_command))
    app.add_handler(CommandHandler("fd", fd_command))
    app.add_handler(CommandHandler("mg", mg_command))
    app.add_handler(CommandHandler("cz", cz_command))
    app.add_handler(CommandHandler("br", br_command))
    app.add_handler(CommandHandler("fn", fn_command))
    app.add_handler(CommandHandler("bp", bp_command))
    app.add_handler(CommandHandler("fl", fl_command))
    app.add_handler(CommandHandler("ts", ts_command))
    app.add_handler(CommandHandler("b3", b3_command))
    app.add_handler(CommandHandler("bb", bb_command))
    app.add_handler(CommandHandler("hr", hr_command))

    # Callback handlers
    app.add_handler(CallbackQueryHandler(show_more_callback, pattern="^show_more"))
    app.add_handler(CallbackQueryHandler(scan_tier_callback, pattern="^scantier_"))
    app.add_handler(CallbackQueryHandler(scan_custom_ev_callback, pattern="^scancustomev_"))
    app.add_handler(CallbackQueryHandler(scan_custom_kelly_callback, pattern="^scancustomkelly_"))
    app.add_handler(CallbackQueryHandler(scan_custom_odds_callback, pattern="^scancustomodds_"))
    app.add_handler(CallbackQueryHandler(resume_tier_callback, pattern="^resumetier_"))
    app.add_handler(CallbackQueryHandler(custom_ev_callback, pattern="^customev_"))
    app.add_handler(CallbackQueryHandler(custom_kelly_callback, pattern="^customkelly_"))
    app.add_handler(CallbackQueryHandler(custom_odds_callback, pattern="^customodds_"))
    app.add_handler(CallbackQueryHandler(interval_callback, pattern="^interval_"))
    app.add_handler(CallbackQueryHandler(toggle_book_callback, pattern="^togglebook_"))
    app.add_handler(CallbackQueryHandler(books_done_callback, pattern="^books_done$"))
    app.add_handler(CallbackQueryHandler(book_tier_callback, pattern="^booktier_"))
    app.add_handler(CallbackQueryHandler(book_custom_ev_callback, pattern="^bookcustomev_"))
    app.add_handler(CallbackQueryHandler(book_custom_kelly_callback, pattern="^bookcustomkelly_"))
    app.add_handler(CallbackQueryHandler(book_custom_odds_callback, pattern="^bookcustomodds_"))

    # Start auto-scan
    async def post_init(app: Application):
        asyncio.create_task(auto_scan_loop(app))

    app.post_init = post_init

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
