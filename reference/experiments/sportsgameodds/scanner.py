"""
NBA Value Scanner - SportsGameOdds Edition
==========================================
Parallel implementation using SportsGameOdds API instead of TheOddsAPI.
Maintains identical de-vig methodology and alert logic.

This is a TEST implementation - runs independently from production scanner.
"""

import os
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Optional
import pandas as pd
import numpy as np
from dotenv import load_dotenv

from provider import (
    SportsGameOddsProvider,
    MarketSnapshot,
    SPORTSGAMEODDS_BOOK_MAPPING,
)

load_dotenv()

# =============================================================================
# CONFIGURATION
# =============================================================================

# Markets to scan (same as production)
MARKETS = [
    'player_double_double',
    'player_triple_double',
    'player_first_basket',
    'player_first_team_basket',
    'player_points_alternate',
    'player_rebounds_alternate',
    'player_assists_alternate',
    'player_blocks_alternate',
    'player_steals_alternate',
    'player_threes_alternate',
]

# Book mapping - includes all SportsGameOdds books plus new additions
BOOK_MAPPING = {
    # From SportsGameOdds provider
    **{k: v for k, v in SPORTSGAMEODDS_BOOK_MAPPING.items()},
}

# Book column order for output (exchanges at end)
BOOK_ORDER = [
    'PN', 'B3',  # Sharp books (Pinnacle, bet365)
    'CI', 'FD', 'DK', 'MG', 'FN', 'CZ', 'ES', 'BB', 'RK', 'BR', 'RB', 'BV', 'BO', 'FL', 'BP',  # Regular books
    'KA', 'NV', 'PX', 'BY'  # Exchanges
]

# Global weights (V10 Pinnacle-Optimized) - MIRRORS PRODUCTION
# Exchanges and international books (B3, KA, NV, PX, BY) have zero weight
# They are used only as bet destinations, not for fair value calculation
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
    # International books - zero weight (not available to US bettors)
    'B3': 0.0000,  # bet365
    # Exchanges - zero weight (used only as bet destinations for alerts)
    'KA': 0.0000,
    'NV': 0.0000,  # novig
    'PX': 0.0000,  # prophetexchange
    'BY': 0.0000,
}

# Default one-way multipliers by odds range
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

# Market-specific multipliers
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

# Extreme longshot multipliers for +3000+
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

# Confidence multipliers by coverage
CONFIDENCE_MULTIPLIERS = {
    1: 0.25, 2: 0.35, 3: 0.47, 4: 0.47, 5: 0.53,
    6: 0.56, 7: 0.62, 8: 0.70, 9: 0.72, 10: 0.81,
    11: 0.81, 12: 0.91, 13: 0.96, 14: 1.00, 15: 1.00,
}

# Alert tier thresholds
ALERT_THRESHOLDS = {
    'FIRE': {'min_kelly': 0.30, 'min_coverage': 8},
    'VALUE_LONGSHOT': {'min_kelly': 0.15, 'min_coverage': 5, 'min_odds': 500},
    'OUTLIER': {'min_kelly': 0.05, 'min_coverage': 3, 'min_pct_vs_next': 35},
}

# State for bet links
STATE = os.getenv('STATE', 'ny').lower()


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
        - If book has both sides available -> use two-way proportional de-vig
        - If book only has one side -> use one-way with multiplier
        Then combine all book fair probabilities using weighted average.

    Returns:
        Tuple of (fair_probability, calc_type)
    """
    if not book_odds:
        return 0.5, 'none'

    weighted_sum = 0
    weight_total = 0
    two_way_count = 0
    one_way_count = 0

    for book_abbrev, data in book_odds.items():
        odds = data['price']
        implied_prob = american_to_probability(odds)

        if implied_prob <= 0:
            continue

        weight = GLOBAL_WEIGHTS.get(book_abbrev, 0.01)

        # Check if this book has the opposite side
        has_opposite = opposite_odds and book_abbrev in opposite_odds

        if has_opposite:
            opp_prob = american_to_probability(opposite_odds[book_abbrev]['price'])

            if opp_prob > 0:
                fair_prob = implied_prob / (implied_prob + opp_prob)
                weighted_sum += fair_prob * weight
                weight_total += weight
                two_way_count += 1
                continue

        # ONE-WAY calculation
        odds_multiplier = get_one_way_multiplier(odds)

        # Extreme longshots (+3000+)
        if odds >= 3000:
            extreme_multiplier = None
            for market_pattern, mult in EXTREME_LONGSHOT_MULTIPLIERS.items():
                if market_pattern in market_key:
                    extreme_multiplier = mult
                    break
            multiplier = extreme_multiplier if extreme_multiplier else odds_multiplier

        # Longshots (+1000 to +2999)
        elif odds >= 1000:
            longshot_multiplier = None
            for market_pattern, mult in LONGSHOT_MARKET_MULTIPLIERS.items():
                if market_pattern in market_key:
                    longshot_multiplier = mult
                    break
            multiplier = longshot_multiplier if longshot_multiplier else odds_multiplier

        else:
            # Non-longshots - check for market-specific multiplier
            market_multiplier = None
            for market_pattern, mult in MARKET_MULTIPLIERS.items():
                if market_pattern in market_key:
                    market_multiplier = mult
                    break

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
    """Calculate how much better the best book is vs the next best."""
    if len(sorted_prices) < 2:
        return 0.0, False

    best_odds = sorted_prices[0][1]
    next_odds = sorted_prices[1][1]

    if best_odds > 0 and next_odds > 0:
        pct_vs_next = ((best_odds - next_odds) / next_odds) * 100
        is_outlier = pct_vs_next >= 35
    else:
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
        'B3': 'https://www.bet365.com',  # NEW
        'BO': 'https://www.betonline.ag',
        'BV': 'https://www.bovada.lv',
        # Exchanges
        'KA': 'https://kalshi.com',
        'NV': 'https://www.novig.us',
        'PX': 'https://www.prophetx.co',
        'BY': 'https://app.betopenly.com',
    }
    return urls.get(book, '')


# =============================================================================
# MAIN SCANNER
# =============================================================================

def scan_for_opportunities(
    state: str = 'pa',
    verbose: bool = True,
    provider: SportsGameOddsProvider = None,
) -> Tuple[pd.DataFrame, Optional[str]]:
    """
    Main scanning function using SportsGameOdds API.

    Returns:
        Tuple of (DataFrame with all opportunities, requests_remaining string)
    """
    global STATE
    STATE = state.lower()

    scan_start_time = time.time()

    if verbose:
        print(f"🔄 Connecting to SportsGameOdds API...")

    # Initialize provider if not passed
    if provider is None:
        api_key = os.getenv('SPORTSGAMEODDS_API_KEY')
        if not api_key:
            if verbose:
                print("❌ SPORTSGAMEODDS_API_KEY not set")
            return pd.DataFrame(), None
        provider = SportsGameOddsProvider(api_key=api_key, mode='rest')

    # Fetch odds
    try:
        snapshots = provider.fetch_nba_odds(markets=MARKETS)
    except Exception as e:
        if verbose:
            print(f"❌ API Error: {e}")
        return pd.DataFrame(), None

    requests_remaining = provider.requests_remaining

    if not snapshots:
        if verbose:
            print("❌ No odds data found.")
        return pd.DataFrame(), requests_remaining

    if verbose:
        print(f"✅ Found {len(snapshots)} unique betting opportunities")
        if requests_remaining:
            print(f"🔑 API Quota: {requests_remaining} requests remaining")

    # Convert snapshots to all_market_data format (matches original scanner)
    all_market_data = {}
    event_info = {}

    for bet_id, snapshot in snapshots.items():
        event = snapshot.event

        # Store event info
        if event.event_id not in event_info:
            event_info[event.event_id] = {
                'home_team': event.home_team,
                'away_team': event.away_team,
                'commence_time': event.commence_time,
                'game': event.game
            }

        # Convert outcomes to format expected by analysis
        market_data = {'market_key': snapshot.market_key}
        for book_abbrev, outcome in snapshot.outcomes.items():
            market_data[book_abbrev] = {
                'price': outcome.price,
                'link': outcome.link,
                'mobile_link': outcome.link,  # TODO: Handle desktop vs mobile links
            }

        all_market_data[bet_id] = market_data

    # Build opposite side lookup
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

        # Extract book odds
        book_odds = {k: v for k, v in data.items() if k != 'market_key'}

        if not book_odds:
            continue

        # Sort by price (highest first)
        sorted_prices = sorted(
            [(abbrev, d['price']) for abbrev, d in book_odds.items()],
            key=lambda x: x[1],
            reverse=True
        )

        if not sorted_prices:
            continue

        best_book, best_odds = sorted_prices[0]
        best_link = book_odds[best_book].get('link', '')
        best_mobile_link = book_odds[best_book].get('mobile_link', best_link)
        coverage = len(book_odds)

        # Get opposite side odds
        opp_odds = opposite_lookup.get(bet_id, None)

        # Calculate fair probability
        fair_prob, calc_type = calculate_fair_probability(book_odds, opp_odds, market_key)

        if calc_type == 'none':
            continue

        fair_odds = probability_to_american(fair_prob)

        # Decimal odds
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

        # Percent vs next
        pct_vs_next, is_outlier = calculate_percent_vs_next(sorted_prices)

        next_best_book = ''
        next_best_odds = 0
        if len(sorted_prices) >= 2:
            next_best_book = sorted_prices[1][0]
            next_best_odds = sorted_prices[1][1]

        # Game time
        game_date, game_time = format_game_time(evt['commence_time'])

        # Best books
        best_books_list = [abbrev for abbrev, price in sorted_prices if price == best_odds]
        best_books_str = ', '.join(best_books_list)

        # Determine alert tier
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

        # Per-book metrics
        per_book_metrics = {}
        qualifying_books_by_tier = {tier: [] for tier in ALERT_THRESHOLDS.keys()}

        for book_abbrev, book_data in book_odds.items():
            book_price = book_data['price']

            if book_price > 0:
                book_decimal = (book_price / 100) + 1
            else:
                book_decimal = (100 / abs(book_price)) + 1

            book_ev = calculate_ev_percentage(fair_prob, book_decimal)

            if book_ev <= 0:
                continue

            book_std_kelly = calculate_kelly(book_ev / 100, book_decimal, fraction=0.25)
            book_conf_kelly = book_std_kelly * conf_multiplier

            per_book_metrics[book_abbrev] = {
                'odds': book_price,
                'ev_pct': round(book_ev, 2),
                'kelly': round(book_std_kelly, 4),
                'conf_kelly': round(book_conf_kelly, 4),
                'link': book_data.get('link', '')
            }

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
            '_link': best_link,
            '_mobile_link': best_mobile_link,
            '_market_key': market_key,
            '_qualifying_books': qualifying_books_by_tier,
            '_book_odds': book_odds,
            '_per_book_metrics': per_book_metrics,
            '_next_best_book': next_best_book,
            '_next_best_odds': next_best_odds,
        }

        # Add individual book columns
        for book_abbrev in BOOK_ORDER:
            if book_abbrev in book_odds:
                record[book_abbrev] = int(book_odds[book_abbrev]['price'])
            else:
                record[book_abbrev] = ''

        opportunities.append(record)

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
        scan_duration = time.time() - scan_start_time
        print(f"\n📊 Total: {len(df)} | +EV: {plus_ev_count}")
        print(f"   Two-way: {two_way_count} | One-way: {one_way_count}")
        print(f"   Scan time: {scan_duration:.2f}s")

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

    # Links
    desktop_link = row.get('_link', '')
    mobile_link = row.get('_mobile_link', '')

    if desktop_link and mobile_link and desktop_link != mobile_link:
        msg += f"⏰ {row['Game Time']} | <a href=\"{desktop_link}\">🖥️ Desktop</a>  ·  <a href=\"{mobile_link}\">📱 Mobile</a>"
    elif desktop_link:
        msg += f"⏰ {row['Game Time']} | <a href=\"{desktop_link}\">Place Bet</a>"
    else:
        msg += f"⏰ {row['Game Time']}"

    # Add provider tag for test comparison
    msg += "\n\n<i>📡 Source: SportsGameOdds</i>"

    return msg


# =============================================================================
# STANDALONE EXECUTION
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("NBA VALUE SCANNER - SPORTSGAMEODDS EDITION")
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
