"""
SportsGameOdds Scanner
======================
Standalone scanner for SportsGameOdds.com API.
Completely separate from production TheOddsAPI scanner.

This scanner:
- Fetches NBA odds from SportsGameOdds REST API
- Calculates fair value using de-vig methodology
- Identifies +EV betting opportunities
- Returns alerts in same format as production scanner
"""

import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import pandas as pd
import numpy as np

from provider import (
    SportsGameOddsRESTClient,
    SPORTSGAMEODDS_BOOK_MAPPING,
    SPORTSGAMEODDS_STAT_MAPPING,
)
from config import (
    SPORTSGAMEODDS_API_KEY,
    STATE,
    EXCLUDED_BOOKS,
)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Target markets - matches production bot where available
# SportsGameOdds stat names -> production equivalents
TARGET_STATS = [
    # Core stats (production: player_X_alternate)
    'points',           # player_points_alternate
    'rebounds',         # player_rebounds_alternate
    'assists',          # player_assists_alternate
    'threePointersMade',# player_threes_alternate
    'blocks',           # player_blocks_alternate
    'steals',           # player_steals_alternate
    # Binary markets (production: player_X)
    'doubleDouble',     # player_double_double
    'tripleDouble',     # player_triple_double
    'firstBasket',      # player_first_basket
    # Note: player_first_team_basket NOT available in SportsGameOdds
]

# Bonus markets (not in production but available here)
BONUS_STATS = [
    'points+rebounds',
    'points+assists',
    'points+rebounds+assists',
    'rebounds+assists',
    'blocks+steals',
    'turnovers',
]

# Book weights for fair value calculation (matches production)
# 0 = not used for fair value, but still available for alerts
BOOK_WEIGHTS = {
    # Sharp books (used for fair value)
    'PN': 10.0,  # Pinnacle - sharpest
    'PX': 7.0,   # ProphetExchange
    'NV': 7.0,   # Novig

    # Major US books
    'DK': 5.0,   # DraftKings
    'FD': 5.0,   # FanDuel
    'MG': 4.0,   # BetMGM
    'CZ': 4.0,   # Caesars
    'ES': 4.0,   # ESPN Bet
    'FN': 3.0,   # Fanatics
    'BR': 3.0,   # BetRivers
    'RK': 3.0,   # Hard Rock
    'BB': 3.0,   # BallyBet
    'BP': 3.0,   # BetParx

    # International - NOT used for fair value, only for alerts
    'B3': 0.0,   # bet365 - alerts only, no weight

    # Offshore - NOT used for fair value, only for alerts
    'BV': 0.0,   # Bovada
    'BO': 0.0,   # BetOnline
}

# Alert thresholds
ALERT_THRESHOLDS = {
    'FIRE': {'min_kelly': 0.30, 'min_coverage': 8},
    'VALUE_LONGSHOT': {'min_kelly': 0.15, 'min_coverage': 5, 'min_odds': 500},
    'OUTLIER': {'min_kelly': 0.05, 'min_coverage': 3, 'min_pct_vs_next': 35},
}

# =============================================================================
# DE-VIG MULTIPLIERS (from production MKB V10 methodology)
# =============================================================================

# Market-specific multipliers for short/medium odds
# Maps SportsGameOdds stat names to multipliers
MARKET_MULTIPLIERS = {
    'doubleDouble': 0.79,           # MKB avg: 0.788
    'tripleDouble': 0.70,           # MKB avg: 0.697
    'firstBasket': 0.81,
    'threePointersMade': 0.76,      # MKB avg for longshots: 0.763
    'rebounds': 0.79,               # MKB avg for longshots: 0.794
    'points': 0.76,                 # MKB avg for longshots: 0.759
    'assists': 0.79,                # MKB avg for longshots: 0.787
    'steals': 0.85,                 # MKB avg: 0.847
    'blocks': 0.87,                 # MKB avg: 0.869
    'blocks+steals': 0.88,
    'points+rebounds+assists': 0.88,
    'rebounds+assists': 0.88,
    'points+rebounds': 0.88,
    'points+assists': 0.88,
}

# Longshot multipliers for 1-way markets at +1000-2999
LONGSHOT_MARKET_MULTIPLIERS = {
    'points': 0.76,
    'threePointersMade': 0.76,
    'assists': 0.79,
    'rebounds': 0.79,
    'steals': 0.85,
    'blocks': 0.87,
    'doubleDouble': 0.79,
    'tripleDouble': 0.70,
}

# Extreme longshot multipliers for +3000 and higher
EXTREME_LONGSHOT_MULTIPLIERS = {
    'points': 0.70,
    'threePointersMade': 0.70,
    'assists': 0.72,
    'rebounds': 0.74,
    'steals': 0.80,
    'blocks': 0.82,
    'doubleDouble': 0.74,
    'tripleDouble': 0.65,
}

# Markets forced to one-way calculation (no two-way de-vig)
FORCE_ONE_WAY_MARKETS = [
    'firstBasket',
    'doubleDouble',
    'tripleDouble',
]

# Confidence multipliers by book coverage
CONFIDENCE_MULTIPLIERS = {
    1: 0.25, 2: 0.35, 3: 0.47, 4: 0.47, 5: 0.53,
    6: 0.56, 7: 0.62, 8: 0.70, 9: 0.72, 10: 0.81,
    11: 0.81, 12: 0.91, 13: 0.96, 14: 1.00, 15: 1.00,
}

# State for bet links
LINK_STATE = STATE.lower()


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


def get_devig_multiplier(stat_id: str, best_odds: int) -> float:
    """
    Get the appropriate de-vig multiplier based on market and odds level.
    Higher odds get more aggressive de-vigging (lower multiplier).
    """
    # Extreme longshots (+3000 and up)
    if best_odds >= 3000:
        return EXTREME_LONGSHOT_MULTIPLIERS.get(stat_id, 0.70)
    # Longshots (+1000 to +2999)
    elif best_odds >= 1000:
        return LONGSHOT_MARKET_MULTIPLIERS.get(stat_id, 0.76)
    # Standard markets
    else:
        return MARKET_MULTIPLIERS.get(stat_id, 0.80)


def calculate_fair_probability(book_odds: Dict[str, int], stat_id: str = None,
                               best_odds: int = None) -> float:
    """
    Calculate fair probability using weighted average of book odds.
    Uses de-vig methodology with book weights and market-specific multipliers.
    """
    if not book_odds:
        return 0.0

    weighted_sum = 0.0
    total_weight = 0.0

    for book, odds in book_odds.items():
        weight = BOOK_WEIGHTS.get(book, 1.0)
        if weight > 0 and odds != 0:
            prob = american_to_probability(odds)
            weighted_sum += prob * weight
            total_weight += weight

    if total_weight == 0:
        return 0.0

    raw_fair_prob = weighted_sum / total_weight

    # Apply de-vig multiplier if stat_id provided
    if stat_id and best_odds:
        multiplier = get_devig_multiplier(stat_id, best_odds)
        # For one-way markets, use the multiplier directly on the implied probability
        if stat_id in FORCE_ONE_WAY_MARKETS:
            return raw_fair_prob * multiplier
        else:
            # For two-way markets, blend with multiplier
            return raw_fair_prob * multiplier

    return raw_fair_prob


def calculate_ev(fair_prob: float, bet_odds: int) -> float:
    """Calculate expected value percentage."""
    if fair_prob <= 0 or bet_odds == 0:
        return 0.0

    implied_prob = american_to_probability(bet_odds)
    if implied_prob <= 0:
        return 0.0

    return ((fair_prob / implied_prob) - 1) * 100


def calculate_kelly(fair_prob: float, bet_odds: int) -> float:
    """Calculate Kelly criterion fraction."""
    if fair_prob <= 0 or bet_odds == 0:
        return 0.0

    if bet_odds > 0:
        b = bet_odds / 100
    else:
        b = 100 / abs(bet_odds)

    q = 1 - fair_prob
    kelly = (b * fair_prob - q) / b

    return max(0, kelly)


def format_market_name(stat_id: str) -> str:
    """Format stat ID to readable market name."""
    mapping = {
        'points': 'Points',
        'rebounds': 'Rebounds',
        'assists': 'Assists',
        'threePointersMade': '3-Pointers',
        'blocks': 'Blocks',
        'steals': 'Steals',
        'doubleDouble': 'Double-Double',
        'tripleDouble': 'Triple-Double',
        'firstBasket': 'First Basket',
        'points+rebounds': 'Pts+Reb',
        'points+assists': 'Pts+Ast',
        'points+rebounds+assists': 'Pts+Reb+Ast',
        'rebounds+assists': 'Reb+Ast',
        'blocks+steals': 'Blk+Stl',
        'turnovers': 'Turnovers',
    }
    return mapping.get(stat_id, stat_id)


def process_link(link: str, book: str, state: str) -> Tuple[str, str]:
    """
    Process bet link for correct state.
    Returns (desktop_link, mobile_link).
    """
    if not link:
        return '', ''

    desktop = link
    mobile = link

    # FanDuel: desktop needs state prefix, mobile doesn't
    if 'fanduel.com' in link:
        if f'{state}.' not in link:
            desktop = link.replace('https://sportsbook.fanduel.com',
                                   f'https://{state}.sportsbook.fanduel.com')
        mobile = link.replace(f'https://{state}.sportsbook.fanduel.com',
                              'https://sportsbook.fanduel.com')

    # BetRivers: needs state
    elif 'betrivers.com' in link:
        import re
        if not re.search(rf'https://{state}\.betrivers\.com', link):
            desktop = re.sub(r'https://([a-z]{2}\.)?betrivers\.com',
                            f'https://{state}.betrivers.com', link)
            mobile = desktop

    # BetMGM: needs state
    elif 'betmgm.com' in link:
        import re
        if not re.search(rf'sports\.{state}\.betmgm\.com', link):
            desktop = re.sub(r'sports\.([a-z]{2}\.)?betmgm\.com',
                            f'sports.{state}.betmgm.com', link)
            mobile = desktop

    # BallyBet: needs state
    elif 'ballybet.com' in link:
        import re
        if not re.search(rf'https://{state}\.ballybet\.com', link):
            desktop = re.sub(r'https://([a-z]{2}\.)?ballybet\.com',
                            f'https://{state}.ballybet.com', link)
            mobile = desktop

    return desktop, mobile


# =============================================================================
# MAIN SCANNER
# =============================================================================

def scan_for_opportunities(
    state: str = 'ny',
    verbose: bool = True
) -> Tuple[pd.DataFrame, Optional[str]]:
    """
    Scan SportsGameOdds for +EV betting opportunities.

    Args:
        state: State abbreviation for bet links
        verbose: Print progress messages

    Returns:
        Tuple of (DataFrame with opportunities, status string)
    """
    global LINK_STATE
    LINK_STATE = state.lower()

    if verbose:
        print("=" * 60)
        print("SportsGameOdds Scanner")
        print("=" * 60)

    # Initialize client
    client = SportsGameOddsRESTClient(api_key=SPORTSGAMEODDS_API_KEY)

    # Fetch events
    if verbose:
        print("\n📡 Fetching NBA events from SportsGameOdds...")

    events = client.get_nba_events()

    if not events:
        if verbose:
            print("❌ No events found with odds")
        return pd.DataFrame(), "No events"

    if verbose:
        print(f"✓ Found {len(events)} events with odds")

    # Process all odds
    all_opportunities = []

    pregame_count = 0
    live_skipped = 0

    for event in events:
        event_id = event.get('eventID', '')
        teams = event.get('teams', {})
        home_team = teams.get('home', {}).get('names', {}).get('medium', 'Unknown')
        away_team = teams.get('away', {}).get('names', {}).get('medium', 'Unknown')
        game = f"{away_team} @ {home_team}"

        status = event.get('status', {})

        # SKIP LIVE GAMES - only process pre-game lines
        # Live odds move too fast and are less reliable
        if status.get('started', False) or status.get('live', False):
            live_skipped += 1
            continue

        pregame_count += 1
        starts_at = status.get('startsAt', '')
        if starts_at:
            try:
                start_time = datetime.fromisoformat(starts_at.replace('Z', '+00:00'))
                # Convert to ET
                start_time_et = start_time - timedelta(hours=5)  # Rough ET conversion
                game_time = start_time_et.strftime('%I:%M %p ET')
            except:
                game_time = 'TBD'
        else:
            game_time = 'TBD'

        players = event.get('players', {})
        odds = event.get('odds', {})

        # Process each odd
        for odd_id, odd_data in odds.items():
            # Parse odd ID: statID-playerID-periodID-betTypeID-sideID
            parts = odd_id.split('-')
            if len(parts) < 5:
                continue

            stat_id = parts[0]
            player_id = parts[1]
            period_id = parts[2]
            bet_type = parts[3]
            side = parts[4]

            # Skip non-player props and non-game period
            if player_id in ['all', 'home', 'away']:
                continue
            if period_id != 'game':
                continue
            # Include TARGET_STATS and BONUS_STATS
            all_stats = TARGET_STATS + BONUS_STATS
            if stat_id not in all_stats:
                continue

            # Get player name
            player_info = players.get(player_id, {})
            player_name = player_info.get('name', player_id.replace('_', ' ').title())

            # Get line
            line = odd_data.get('fairOverUnder') or odd_data.get('bookOverUnder') or '0'
            try:
                line = float(line)
            except:
                line = 0

            # Collect odds from all books
            by_bookmaker = odd_data.get('byBookmaker', {})
            book_odds = {}
            book_links = {}

            for book_key, book_data in by_bookmaker.items():
                if book_key == 'unknown':
                    continue

                book_abbrev = SPORTSGAMEODDS_BOOK_MAPPING.get(book_key)
                if not book_abbrev:
                    continue

                odds_str = book_data.get('odds', '')
                if not odds_str:
                    continue

                try:
                    odds_val = int(odds_str)
                except:
                    continue

                book_odds[book_abbrev] = odds_val

                # Get deep link if available
                deeplink = book_data.get('deeplink', '')
                if deeplink:
                    book_links[book_abbrev] = deeplink

            # Need at least 2 books for fair value
            if len(book_odds) < 2:
                continue

            # Find best odds first (excluding sharp books for betting)
            best_book = None
            best_odds = None
            best_link = ''

            for book, odds_val in book_odds.items():
                if book in EXCLUDED_BOOKS:
                    continue
                if best_odds is None or odds_val > best_odds:
                    best_odds = odds_val
                    best_book = book
                    best_link = book_links.get(book, '')

            if best_book is None or best_odds is None:
                continue

            # Calculate fair value with market-specific de-vig
            fair_prob = calculate_fair_probability(book_odds, stat_id, best_odds)
            if fair_prob <= 0:
                continue

            fair_odds = probability_to_american(fair_prob)

            if best_book is None:
                continue

            # Calculate metrics
            ev = calculate_ev(fair_prob, best_odds)
            kelly = calculate_kelly(fair_prob, best_odds)
            coverage = len(book_odds)

            # Skip if negative EV
            if ev <= 0:
                continue

            # Determine alert tier
            alert_tier = None

            # Check FIRE tier
            if kelly >= ALERT_THRESHOLDS['FIRE']['min_kelly'] and \
               coverage >= ALERT_THRESHOLDS['FIRE']['min_coverage']:
                alert_tier = 'FIRE'

            # Check VALUE_LONGSHOT tier
            elif kelly >= ALERT_THRESHOLDS['VALUE_LONGSHOT']['min_kelly'] and \
                 coverage >= ALERT_THRESHOLDS['VALUE_LONGSHOT']['min_coverage'] and \
                 best_odds >= ALERT_THRESHOLDS['VALUE_LONGSHOT']['min_odds']:
                alert_tier = 'VALUE_LONGSHOT'

            # Check OUTLIER tier
            elif kelly >= ALERT_THRESHOLDS['OUTLIER']['min_kelly'] and \
                 coverage >= ALERT_THRESHOLDS['OUTLIER']['min_coverage']:
                # Calculate % vs next best
                sorted_odds = sorted(book_odds.values(), reverse=True)
                if len(sorted_odds) >= 2:
                    best = sorted_odds[0]
                    next_best = sorted_odds[1]
                    if next_best != 0:
                        pct_vs_next = ((best - next_best) / abs(next_best)) * 100
                        if pct_vs_next >= ALERT_THRESHOLDS['OUTLIER']['min_pct_vs_next']:
                            alert_tier = 'OUTLIER'

            # Process link
            desktop_link, mobile_link = process_link(best_link, best_book, LINK_STATE)

            # Create opportunity record
            opportunity = {
                'Player': player_name,
                'Market': format_market_name(stat_id),
                'Side': side.upper(),
                'Line': line,
                'Best Odds': best_odds,
                'Fair Odds': fair_odds,
                'EV %': ev,
                'Kelly': kelly,
                'Conf. Adj. Recc. U': kelly * 0.25,  # Quarter Kelly
                'Coverage': coverage,
                'Best Books': best_book,
                'Alert Tier': alert_tier,
                'Game': game,
                'Game Time': game_time,
                '_link': desktop_link,
                '_mobile_link': mobile_link,
                '_event_id': event_id,
                '_book_odds': book_odds,
            }

            all_opportunities.append(opportunity)

    # Create DataFrame
    if not all_opportunities:
        if verbose:
            print("❌ No +EV opportunities found")
        return pd.DataFrame(), "No opportunities"

    df = pd.DataFrame(all_opportunities)

    # Sort by Kelly (best first)
    df = df.sort_values('Kelly', ascending=False)

    if verbose:
        print(f"\n📊 Processed {pregame_count} pre-game events")
        if live_skipped > 0:
            print(f"   (skipped {live_skipped} live/in-play games)")
        print(f"✓ Found {len(df)} +EV opportunities")
        alerts = df[df['Alert Tier'].notna()]
        print(f"✓ {len(alerts)} meet alert thresholds")

        # Show tier breakdown
        for tier in ['FIRE', 'VALUE_LONGSHOT', 'OUTLIER']:
            count = len(df[df['Alert Tier'] == tier])
            if count > 0:
                emoji = {'FIRE': '🔥', 'VALUE_LONGSHOT': '🎯', 'OUTLIER': '⚡'}[tier]
                print(f"   {emoji} {tier}: {count}")

    # Get usage info
    usage = client.get_account_usage()
    status_str = None
    if usage and 'data' in usage:
        rate = usage['data'].get('rateLimits', {}).get('per-hour', {})
        current = rate.get('current-requests', '?')
        max_req = rate.get('max-requests', '?')
        status_str = f"{current}/{max_req} requests this hour"

    return df, status_str


def get_alerts(df: pd.DataFrame) -> pd.DataFrame:
    """Filter DataFrame to only alertable opportunities."""
    if df.empty:
        return df
    return df[df['Alert Tier'].notna()].copy()


def format_alert_message(row: pd.Series) -> str:
    """Format a single opportunity as a Telegram message."""
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
    msg += f"📚 {row['Best Books']} | Coverage: {row['Coverage']}\n"
    msg += f"🏀 {row['Game']}\n"

    # Add bet links
    desktop_link = row.get('_link', '')
    mobile_link = row.get('_mobile_link', '')

    if desktop_link and mobile_link and desktop_link != mobile_link:
        msg += f"⏰ {row['Game Time']} | <a href=\"{desktop_link}\">🖥️ Desktop</a>  ·  <a href=\"{mobile_link}\">📱 Mobile</a>"
    elif desktop_link:
        msg += f"⏰ {row['Game Time']} | <a href=\"{desktop_link}\">Place Bet</a>"
    else:
        msg += f"⏰ {row['Game Time']}"

    return msg


# =============================================================================
# STANDALONE EXECUTION
# =============================================================================

if __name__ == "__main__":
    print("\nSPORTSGAMEODDS SCANNER")
    print("=" * 60)

    state = input("Enter state (default: ny): ").strip() or 'ny'

    df, status = scan_for_opportunities(state=state, verbose=True)

    if not df.empty:
        print("\n" + "=" * 60)
        print("TOP OPPORTUNITIES")
        print("=" * 60)

        alerts = get_alerts(df)
        for idx, row in alerts.head(10).iterrows():
            print("\n" + format_alert_message(row))
            print("-" * 40)

    if status:
        print(f"\n📊 API Status: {status}")
