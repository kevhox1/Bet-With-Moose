#!/usr/bin/env python3
"""
SportsGameOdds WebSocket Bot
============================
Real-time odds scanner using Pusher WebSocket + Telegram alerts.
Full-featured bot matching production UI (without bet tracking).

Run locally on Mac:
    pip install -r requirements.txt
    python websocket_bot.py
"""

import os
import sys
import json
import time
import asyncio
import logging
import threading
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Any
from collections import defaultdict

# Pusher client
try:
    import pysher
    PYSHER_AVAILABLE = True
except ImportError:
    PYSHER_AVAILABLE = False
    print("pysher not installed. Run: pip install pysher")

# Telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

# =============================================================================
# CONFIGURATION
# =============================================================================

# SportsGameOdds API
API_KEY = "7546525eada0352b926e60dbc6c42cb0"
API_BASE_URL = "https://api.sportsgameodds.com/v2"

# Telegram (Test channel)
TELEGRAM_BOT_TOKEN = "8433115695:AAHIY27eEnfKMaL-SsVQL5dXUKuewpSpm18"
TELEGRAM_CHAT_ID = "-1003336875829"

# Supported states for links
SUPPORTED_STATES = ['ny', 'pa', 'nj']

# Default state
DEFAULT_STATE = "ny"

# Scanning Settings
SCAN_INTERVAL_SECONDS = 10  # 10 seconds

# Active hours (Eastern Time)
ACTIVE_HOURS_START = 8   # 8 AM EST
ACTIVE_HOURS_END = 24    # Midnight EST

# Alert thresholds
ALERT_THRESHOLDS = {
    'FIRE': {'min_kelly': 0.30, 'min_coverage': 8},
    'VALUE_LONGSHOT': {'min_kelly': 0.15, 'min_coverage': 5, 'min_odds': 500},
    'OUTLIER': {'min_kelly': 0.05, 'min_coverage': 3, 'min_pct_vs_next': 35},
}

# Book weights for fair value calculation
BOOK_WEIGHTS = {
    'pinnacle': 10.0, 'prophetexchange': 7.0, 'novig': 7.0,
    'draftkings': 5.0, 'fanduel': 5.0, 'betmgm': 4.0, 'caesars': 4.0,
    'espnbet': 4.0, 'fanatics': 3.0, 'betrivers': 3.0, 'hardrockbet': 3.0,
    'ballybet': 3.0, 'betparx': 3.0, 'bet365': 0.0, 'bovada': 0.0,
}

# Books excluded from best odds (sharp books)
EXCLUDED_BOOKS = ['pinnacle']

# Player prop stats we care about
PLAYER_PROP_STATS = [
    'points', 'rebounds', 'assists', 'threePointersMade', 'blocks', 'steals',
    'doubleDouble', 'tripleDouble', 'firstBasket',
    'points+rebounds', 'points+assists', 'points+rebounds+assists'
]

# De-vig multipliers by market
MARKET_MULTIPLIERS = {
    'doubleDouble': 0.79, 'tripleDouble': 0.70, 'firstBasket': 0.81,
    'threePointersMade': 0.76, 'rebounds': 0.79, 'points': 0.76,
    'assists': 0.79, 'steals': 0.85, 'blocks': 0.87,
}

# Book display config
BOOK_CONFIG = {
    'draftkings': {'abbrev': 'DK', 'name': 'DraftKings', 'state_url': False},
    'fanduel': {'abbrev': 'FD', 'name': 'FanDuel', 'state_url': True, 'desktop_mobile_split': True},
    'betmgm': {'abbrev': 'MG', 'name': 'BetMGM', 'state_url': True},
    'caesars': {'abbrev': 'CZ', 'name': 'Caesars', 'state_url': False},
    'espnbet': {'abbrev': 'ES', 'name': 'ESPN BET', 'state_url': False},
    'fanatics': {'abbrev': 'FN', 'name': 'Fanatics', 'state_url': False},
    'betrivers': {'abbrev': 'BR', 'name': 'BetRivers', 'state_url': True},
    'hardrockbet': {'abbrev': 'RK', 'name': 'Hard Rock', 'state_url': False},
    'ballybet': {'abbrev': 'BB', 'name': 'BallyBet', 'state_url': True},
    'betparx': {'abbrev': 'BP', 'name': 'BetParx', 'state_url': False},
    'pinnacle': {'abbrev': 'PN', 'name': 'Pinnacle', 'state_url': False},
    'fliff': {'abbrev': 'FL', 'name': 'Fliff', 'state_url': False},
}

# Reverse lookup: abbrev -> book_key
ABBREV_TO_BOOK = {v['abbrev']: k for k, v in BOOK_CONFIG.items()}

# =============================================================================
# LOGGING
# =============================================================================

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('websocket_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =============================================================================
# GLOBALS
# =============================================================================

events_cache: Dict[str, dict] = {}  # eventID -> event data
sent_alerts: Dict[str, dict] = {}   # alert_key -> {ev_pct, timestamp}
last_scan_results: List[dict] = []  # Store last scan for "show more"
last_scan_index: int = 0            # Current index for pagination
pusher_client = None
updates_received = 0
auto_scan_enabled = True
current_state = DEFAULT_STATE

# Custom scan state (for wizard)
custom_scan_state: Dict[int, dict] = {}  # chat_id -> {min_ev, min_kelly, etc}

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
    """Get de-vig multiplier based on market and odds level."""
    base = MARKET_MULTIPLIERS.get(stat_id, 0.76)
    if best_odds >= 3000:
        return base - 0.06
    elif best_odds >= 1000:
        return base
    else:
        return min(base + 0.04, 0.85)


def calculate_fair_probability(book_odds: Dict[str, int], stat_id: str, best_odds: int) -> float:
    """Calculate fair probability using weighted average."""
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
    multiplier = get_devig_multiplier(stat_id, best_odds)
    return raw_fair_prob * multiplier


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


def calculate_ev(fair_prob: float, bet_odds: int) -> float:
    """Calculate expected value percentage."""
    if fair_prob <= 0 or bet_odds == 0:
        return 0.0
    implied_prob = american_to_probability(bet_odds)
    if implied_prob <= 0:
        return 0.0
    return ((fair_prob / implied_prob) - 1) * 100


def format_stat_name(stat_id: str) -> str:
    """Format stat ID to readable name."""
    mapping = {
        'points': 'Points', 'rebounds': 'Rebounds', 'assists': 'Assists',
        'threePointersMade': '3-Pointers', 'blocks': 'Blocks', 'steals': 'Steals',
        'doubleDouble': 'Double-Double', 'tripleDouble': 'Triple-Double',
        'firstBasket': 'First Basket', 'points+rebounds': 'Pts+Reb',
        'points+assists': 'Pts+Ast', 'points+rebounds+assists': 'PRA',
    }
    return mapping.get(stat_id, stat_id)


def get_event_title(event: dict) -> str:
    """Format event title."""
    away = event.get('teams', {}).get('away', {}).get('names', {}).get('medium', 'Away')
    home = event.get('teams', {}).get('home', {}).get('names', {}).get('medium', 'Home')
    return f"{away} @ {home}"


def get_game_time(event: dict) -> str:
    """Get formatted game time in ET."""
    starts_at = event.get('status', {}).get('startsAt', '')
    if starts_at:
        try:
            start_time = datetime.fromisoformat(starts_at.replace('Z', '+00:00'))
            start_time_et = start_time - timedelta(hours=5)
            return start_time_et.strftime('%I:%M %p ET')
        except:
            pass
    return 'TBD'


def is_active_hours() -> bool:
    """Check if current time is within active scanning hours."""
    utc_now = datetime.now(timezone.utc)
    est_now = utc_now - timedelta(hours=5)
    current_hour = est_now.hour

    if ACTIVE_HOURS_END > ACTIVE_HOURS_START:
        return ACTIVE_HOURS_START <= current_hour < ACTIVE_HOURS_END
    else:
        return current_hour >= ACTIVE_HOURS_START or current_hour < ACTIVE_HOURS_END


def generate_alert_key(player: str, stat: str, line: str, side: str, book: str) -> str:
    """Generate unique key for an alert."""
    return f"{player}|{stat}|{line}|{side}|{book}"


def should_send_alert(alert_key: str, ev_pct: float) -> bool:
    """Check if we should send this alert (avoid duplicates)."""
    if alert_key not in sent_alerts:
        return True

    previous = sent_alerts[alert_key]
    time_since = (datetime.now(timezone.utc) - previous['timestamp']).total_seconds() / 60

    if time_since >= 30:
        ev_improvement = ev_pct - previous['ev_pct']
        if ev_improvement >= 3.0:
            return True

    return False


# =============================================================================
# MULTI-STATE LINK GENERATION
# =============================================================================

def generate_state_url(book_key: str, state: str, base_link: str = "") -> str:
    """Generate state-specific URL for a sportsbook."""
    state = state.lower()

    # URL patterns by book
    if book_key == 'fanduel':
        return f"https://{state}.sportsbook.fanduel.com/"
    elif book_key == 'betmgm':
        return f"https://sports.{state}.betmgm.com/"
    elif book_key == 'betrivers':
        return f"https://{state}.betrivers.com/"
    elif book_key == 'ballybet':
        return f"https://{state}.ballybet.com/"
    elif book_key == 'draftkings':
        return "https://sportsbook.draftkings.com/"
    else:
        return base_link or ""


def generate_multi_state_links(book_key: str, base_link: str = "") -> str:
    """Generate multi-state links for alert message."""
    config = BOOK_CONFIG.get(book_key, {})
    abbrev = config.get('abbrev', book_key.upper())

    if not config.get('state_url', False):
        # Book doesn't need state-specific URLs
        link = base_link or generate_state_url(book_key, 'ny')
        if link:
            return f"🔗 <a href=\"{link}\">Place Bet</a>"
        return f"📚 {abbrev}"

    # FanDuel special case: desktop and mobile links
    if config.get('desktop_mobile_split', False):
        desktop_links = []
        for state in SUPPORTED_STATES:
            url = generate_state_url(book_key, state)
            desktop_links.append(f"<a href=\"{url}\">{state.upper()}</a>")

        mobile_url = "https://sportsbook.fanduel.com/"
        return (
            f"🖥️ Desktop: {' · '.join(desktop_links)}\n"
            f"📱 <a href=\"{mobile_url}\">Mobile</a>"
        )

    # Standard multi-state links
    links = []
    for state in SUPPORTED_STATES:
        url = generate_state_url(book_key, state, base_link)
        links.append(f"<a href=\"{url}\">{state.upper()}</a>")

    return f"🔗 {' · '.join(links)}"


# =============================================================================
# API FUNCTIONS
# =============================================================================

def api_request(endpoint: str, params: dict = None) -> Optional[dict]:
    """Make API request with retry logic."""
    url = f"{API_BASE_URL}{endpoint}"
    headers = {'x-api-key': API_KEY}

    for attempt in range(3):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 503:
                logger.warning(f"API 503, retry {attempt+1}/3...")
                time.sleep(2 * (attempt + 1))
            else:
                logger.error(f"API error {response.status_code}: {response.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"Request failed: {e}")
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    return None


def get_stream_config() -> Optional[dict]:
    """Get WebSocket stream configuration."""
    return api_request("/stream/events", {"feed": "events:upcoming", "leagueID": "NBA"})


def fetch_events(event_ids: List[str] = None) -> List[dict]:
    """Fetch event data."""
    params = {"leagueID": "NBA", "ended": "false"}
    if event_ids:
        params["eventIDs"] = ",".join(event_ids)

    result = api_request("/events", params)
    if result and 'data' in result:
        return result['data']
    return []


# =============================================================================
# SCANNER LOGIC
# =============================================================================

def scan_event_for_opportunities(event: dict, book_filter: str = None) -> List[dict]:
    """Scan a single event for +EV opportunities."""
    opportunities = []

    event_id = event.get('eventID', '')
    game = get_event_title(event)
    game_time = get_game_time(event)

    # Skip live games
    status = event.get('status', {})
    if status.get('started', False) or status.get('live', False):
        return []

    players = event.get('players', {})
    odds = event.get('odds', {})

    for odd_id, odd_data in odds.items():
        parts = odd_id.split('-')
        if len(parts) < 5:
            continue

        stat_id, player_id, period, bet_type, side = parts[:5]

        if player_id in ['all', 'home', 'away']:
            continue
        if period != 'game':
            continue
        if stat_id not in PLAYER_PROP_STATS:
            continue

        player_info = players.get(player_id, {})
        player_name = player_info.get('name', player_id.replace('_', ' ').title())

        line = odd_data.get('fairOverUnder') or odd_data.get('bookOverUnder') or '0'
        try:
            line = float(line)
        except:
            line = 0

        by_bookmaker = odd_data.get('byBookmaker', {})
        book_odds = {}
        book_links = {}

        for book_key, book_data in by_bookmaker.items():
            if book_key == 'unknown':
                continue

            price = book_data.get('price') or book_data.get('odds')
            if not price:
                continue

            try:
                price = int(price)
            except:
                continue

            book_odds[book_key] = price
            deeplink = book_data.get('deeplink', '')
            if deeplink:
                book_links[book_key] = deeplink

        if len(book_odds) < 2:
            continue

        # If filtering by book, only consider that book for best odds
        if book_filter:
            book_key_filter = ABBREV_TO_BOOK.get(book_filter.upper(), book_filter.lower())
            if book_key_filter not in book_odds:
                continue
            best_book = book_key_filter
            best_odds = book_odds[book_key_filter]
            best_link = book_links.get(book_key_filter, '')
        else:
            # Find best odds (excluding sharp books)
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

        fair_prob = calculate_fair_probability(book_odds, stat_id, best_odds)
        if fair_prob <= 0:
            continue

        fair_odds = probability_to_american(fair_prob)
        ev = calculate_ev(fair_prob, best_odds)
        kelly = calculate_kelly(fair_prob, best_odds)
        coverage = len(book_odds)

        if ev <= 0:
            continue

        # Determine alert tier
        alert_tier = None

        if kelly >= ALERT_THRESHOLDS['FIRE']['min_kelly'] and \
           coverage >= ALERT_THRESHOLDS['FIRE']['min_coverage']:
            alert_tier = 'FIRE'
        elif kelly >= ALERT_THRESHOLDS['VALUE_LONGSHOT']['min_kelly'] and \
             coverage >= ALERT_THRESHOLDS['VALUE_LONGSHOT']['min_coverage'] and \
             best_odds >= ALERT_THRESHOLDS['VALUE_LONGSHOT']['min_odds']:
            alert_tier = 'VALUE_LONGSHOT'
        elif kelly >= ALERT_THRESHOLDS['OUTLIER']['min_kelly'] and \
             coverage >= ALERT_THRESHOLDS['OUTLIER']['min_coverage']:
            sorted_odds = sorted(book_odds.values(), reverse=True)
            if len(sorted_odds) >= 2:
                pct_vs_next = ((sorted_odds[0] - sorted_odds[1]) / max(abs(sorted_odds[1]), 1)) * 100
                if pct_vs_next >= ALERT_THRESHOLDS['OUTLIER']['min_pct_vs_next']:
                    alert_tier = 'OUTLIER'

        opportunities.append({
            'player': player_name,
            'stat': stat_id,
            'side': side.upper(),
            'line': line,
            'best_odds': best_odds,
            'fair_odds': fair_odds,
            'ev': ev,
            'kelly': kelly,
            'units': kelly * 0.25,
            'coverage': coverage,
            'best_book': best_book,
            'tier': alert_tier,
            'game': game,
            'game_time': game_time,
            'link': best_link,
            'all_odds': book_odds,
        })

    return opportunities


def run_full_scan(book_filter: str = None) -> List[dict]:
    """Run a full scan across all events."""
    global events_cache

    all_opportunities = []

    # Use cached events or fetch fresh
    if events_cache:
        events = list(events_cache.values())
    else:
        events = fetch_events()
        for event in events:
            events_cache[event.get('eventID')] = event

    for event in events:
        opps = scan_event_for_opportunities(event, book_filter)
        all_opportunities.extend(opps)

    # Sort by kelly descending
    all_opportunities.sort(key=lambda x: x['kelly'], reverse=True)

    return all_opportunities


# =============================================================================
# MESSAGE FORMATTING
# =============================================================================

def format_alert_message(opp: dict, include_links: bool = True) -> str:
    """Format opportunity as Telegram message with multi-state links."""
    tier_emoji = {'FIRE': '🔥', 'VALUE_LONGSHOT': '🎯', 'OUTLIER': '⚡'}.get(opp.get('tier'), '📊')
    book_key = opp['best_book']
    book_abbrev = BOOK_CONFIG.get(book_key, {}).get('abbrev', book_key.upper())

    msg = f"{tier_emoji} <b>{opp['player']}</b>\n"
    msg += f"📍 {format_stat_name(opp['stat'])} {opp['side']}"
    if opp['line']:
        msg += f" {opp['line']}"
    msg += f"\n\n"

    msg += f"💵 <b>{opp['best_odds']:+d}</b> @ {book_abbrev} (Fair: {opp['fair_odds']:+d})\n"
    msg += f"📈 EV: {opp['ev']:.1f}% | Kelly: {opp['kelly']:.2f} | Units: {opp['units']:.2f}\n"
    msg += f"📚 Coverage: {opp['coverage']} books\n"
    msg += f"🏀 {opp['game']} | {opp['game_time']}\n\n"

    if include_links:
        msg += generate_multi_state_links(book_key, opp.get('link', ''))

    return msg


def format_scan_summary(opportunities: List[dict], tier_filter: str = None) -> str:
    """Format scan summary message."""
    if tier_filter and tier_filter != 'ALL':
        filtered = [o for o in opportunities if o.get('tier') == tier_filter]
    else:
        filtered = opportunities

    tier_counts = {'FIRE': 0, 'VALUE_LONGSHOT': 0, 'OUTLIER': 0, None: 0}
    for opp in opportunities:
        tier = opp.get('tier')
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    msg = "📊 <b>Scan Results</b>\n\n"
    msg += f"🔥 Fire: {tier_counts['FIRE']}\n"
    msg += f"🎯 Value Longshot: {tier_counts['VALUE_LONGSHOT']}\n"
    msg += f"⚡ Outlier: {tier_counts['OUTLIER']}\n"
    msg += f"📈 Other +EV: {tier_counts[None]}\n\n"
    msg += f"<b>Total: {len(opportunities)}</b>"

    if tier_filter and tier_filter != 'ALL':
        msg += f"\n\n<i>Showing: {tier_filter} only ({len(filtered)} results)</i>"

    return msg


# =============================================================================
# BOT COMMANDS
# =============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    keyboard = [
        [InlineKeyboardButton("🔍 Scan Now", callback_data="scan_menu")],
        [InlineKeyboardButton("📊 Status", callback_data="status")],
        [
            InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
            InlineKeyboardButton("❓ Help", callback_data="help"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = (
        "🏀 <b>NBA Value Scanner</b>\n"
        "<i>SportsGameOdds WebSocket Edition</i>\n\n"
        f"📡 Mode: Real-time WebSocket\n"
        f"📍 State: {current_state.upper()}\n"
        f"🔄 Auto-scan: {'Enabled' if auto_scan_enabled else 'Disabled'}\n\n"
        "Select an option below:"
    )

    await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /scan command - show tier selection."""
    keyboard = [
        [
            InlineKeyboardButton("🔥 Fire", callback_data="scan_FIRE"),
            InlineKeyboardButton("🎯 Longshot", callback_data="scan_VALUE_LONGSHOT"),
            InlineKeyboardButton("⚡ Outlier", callback_data="scan_OUTLIER"),
        ],
        [
            InlineKeyboardButton("📊 All", callback_data="scan_ALL"),
            InlineKeyboardButton("🔒 Custom", callback_data="scan_CUSTOM"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = (
        "🔍 <b>Manual Scan</b>\n\n"
        "Select alert tier to show:\n\n"
        "🔥 <b>Fire</b> - Kelly ≥0.30, 8+ books\n"
        "🎯 <b>Longshot</b> - Kelly ≥0.15, 5+ books, +500+\n"
        "⚡ <b>Outlier</b> - Kelly ≥0.05, 35%+ edge vs next\n"
        "📊 <b>All</b> - Show all +EV opportunities\n"
        "🔒 <b>Custom</b> - Set your own filters"
    )

    await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command."""
    utc_now = datetime.now(timezone.utc)
    est_now = utc_now - timedelta(hours=5)

    active = "✅ Active" if is_active_hours() else "⏸️ Outside hours"

    msg = (
        "📊 <b>Bot Status</b>\n\n"
        f"📡 <b>Provider:</b> SportsGameOdds\n"
        f"🔄 <b>Mode:</b> WebSocket (Real-time)\n"
        f"📍 <b>State:</b> {current_state.upper()}\n\n"
        f"⏰ <b>Time:</b> {est_now.strftime('%I:%M %p')} EST\n"
        f"📅 <b>Active Hours:</b> {ACTIVE_HOURS_START}:00 - {ACTIVE_HOURS_END}:00 EST\n"
        f"📊 <b>Status:</b> {active}\n\n"
        f"🔔 <b>Auto-Scan:</b> {'Enabled' if auto_scan_enabled else 'Disabled'}\n"
        f"⏱️ <b>Interval:</b> {SCAN_INTERVAL_SECONDS}s\n"
        f"🎮 <b>Events Cached:</b> {len(events_cache)}\n"
        f"📝 <b>Alerts Sent:</b> {len(sent_alerts)}\n"
        f"📡 <b>Updates Received:</b> {updates_received}"
    )

    if update.message:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    elif update.callback_query:
        await update.callback_query.message.reply_text(msg, parse_mode=ParseMode.HTML)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    msg = (
        "🏀 <b>NBA Value Scanner - Help</b>\n\n"
        "<b>Commands:</b>\n"
        "/start - Main menu\n"
        "/scan - Scan for opportunities\n"
        "/status - Bot status\n"
        "/setstate &lt;XX&gt; - Change state (ny, pa, nj)\n"
        "/toggle - Enable/disable auto-scan\n"
        "/books - Show available books\n"
        "/help - This help message\n\n"
        "<b>Book Commands:</b>\n"
        "/dk - DraftKings only\n"
        "/fd - FanDuel only\n"
        "/mg - BetMGM only\n"
        "/cz - Caesars only\n"
        "/es - ESPN BET only\n"
        "/fn - Fanatics only\n"
        "/br - BetRivers only\n"
        "/bb - BallyBet only\n"
        "/fl - Fliff only\n\n"
        "<b>Alert Tiers:</b>\n"
        "🔥 Fire - Kelly ≥0.30, 8+ books\n"
        "🎯 Longshot - Kelly ≥0.15, 5+ books, +500+\n"
        "⚡ Outlier - 35%+ better than next best\n\n"
        "<i>Powered by SportsGameOdds WebSocket</i>"
    )

    if update.message:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    elif update.callback_query:
        await update.callback_query.message.reply_text(msg, parse_mode=ParseMode.HTML)


async def setstate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /setstate command."""
    global current_state

    if not context.args:
        await update.message.reply_text(
            f"Current state: <b>{current_state.upper()}</b>\n\n"
            f"Usage: /setstate &lt;state_code&gt;\n"
            f"Supported: {', '.join(s.upper() for s in SUPPORTED_STATES)}",
            parse_mode=ParseMode.HTML
        )
        return

    new_state = context.args[0].lower()

    if new_state not in SUPPORTED_STATES:
        await update.message.reply_text(
            f"❌ State '{new_state.upper()}' not supported for links.\n\n"
            f"Supported states: {', '.join(s.upper() for s in SUPPORTED_STATES)}\n\n"
            f"<i>Setting anyway for reference...</i>",
            parse_mode=ParseMode.HTML
        )

    current_state = new_state
    await update.message.reply_text(f"✅ State set to: <b>{current_state.upper()}</b>", parse_mode=ParseMode.HTML)


async def toggle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /toggle command."""
    global auto_scan_enabled
    auto_scan_enabled = not auto_scan_enabled
    status = "enabled ✅" if auto_scan_enabled else "disabled ⏸️"
    await update.message.reply_text(f"🔄 Auto-scan {status}", parse_mode=ParseMode.HTML)


async def books_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /books command."""
    msg = "📚 <b>Available Sportsbooks</b>\n\n"

    for book_key, config in BOOK_CONFIG.items():
        if book_key == 'pinnacle':
            continue  # Skip sharp books
        abbrev = config['abbrev']
        name = config['name']
        state_note = " (state links)" if config.get('state_url') else ""
        msg += f"/{abbrev.lower()} - {name}{state_note}\n"

    msg += "\n<i>Use /{book} to scan for that book only</i>"

    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


# Book-specific commands
async def book_scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE, book_abbrev: str, book_name: str):
    """Generic book-specific scan command."""
    keyboard = [
        [
            InlineKeyboardButton("🔥", callback_data=f"bookscan_{book_abbrev}_FIRE"),
            InlineKeyboardButton("🎯", callback_data=f"bookscan_{book_abbrev}_VALUE_LONGSHOT"),
            InlineKeyboardButton("⚡", callback_data=f"bookscan_{book_abbrev}_OUTLIER"),
        ],
        [
            InlineKeyboardButton("📊 All", callback_data=f"bookscan_{book_abbrev}_ALL"),
            InlineKeyboardButton("🔒 Custom", callback_data=f"bookscan_{book_abbrev}_CUSTOM"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = f"🔍 <b>{book_name} Scan</b>\n\nSelect alert tier:"
    await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def dk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await book_scan_command(update, context, "DK", "DraftKings")

async def fd_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await book_scan_command(update, context, "FD", "FanDuel")

async def mg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await book_scan_command(update, context, "MG", "BetMGM")

async def cz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await book_scan_command(update, context, "CZ", "Caesars")

async def es_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await book_scan_command(update, context, "ES", "ESPN BET")

async def fn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await book_scan_command(update, context, "FN", "Fanatics")

async def br_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await book_scan_command(update, context, "BR", "BetRivers")

async def bb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await book_scan_command(update, context, "BB", "BallyBet")

async def fl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await book_scan_command(update, context, "FL", "Fliff")


# =============================================================================
# CALLBACK HANDLERS
# =============================================================================

async def scan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle scan tier selection."""
    global last_scan_results, last_scan_index

    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "scan_menu":
        # Show scan menu
        keyboard = [
            [
                InlineKeyboardButton("🔥 Fire", callback_data="scan_FIRE"),
                InlineKeyboardButton("🎯 Longshot", callback_data="scan_VALUE_LONGSHOT"),
                InlineKeyboardButton("⚡ Outlier", callback_data="scan_OUTLIER"),
            ],
            [
                InlineKeyboardButton("📊 All", callback_data="scan_ALL"),
                InlineKeyboardButton("🔒 Custom", callback_data="scan_CUSTOM"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(
            "🔍 <b>Select Scan Type</b>",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        return

    if data == "scan_CUSTOM":
        # Start custom wizard - EV selection
        keyboard = [
            [
                InlineKeyboardButton("5%", callback_data="customev_5"),
                InlineKeyboardButton("10%", callback_data="customev_10"),
                InlineKeyboardButton("15%", callback_data="customev_15"),
            ],
            [
                InlineKeyboardButton("20%", callback_data="customev_20"),
                InlineKeyboardButton("25%", callback_data="customev_25"),
                InlineKeyboardButton(">0%", callback_data="customev_0"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(
            "🔒 <b>Custom Scan</b>\n\nStep 1/3: Select minimum EV%:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        return

    # Extract tier
    tier = data.replace("scan_", "")

    await query.message.reply_text("🔄 Scanning...", parse_mode=ParseMode.HTML)

    # Run scan
    opportunities = run_full_scan()

    if not opportunities:
        await query.message.reply_text("❌ No opportunities found.", parse_mode=ParseMode.HTML)
        return

    # Filter by tier
    if tier != 'ALL':
        filtered = [o for o in opportunities if o.get('tier') == tier]
    else:
        filtered = opportunities

    # Send summary
    await query.message.reply_text(format_scan_summary(opportunities, tier), parse_mode=ParseMode.HTML)

    if not filtered:
        await query.message.reply_text(f"No {tier} alerts found.", parse_mode=ParseMode.HTML)
        return

    # Store for pagination
    last_scan_results = filtered
    last_scan_index = 0

    # Send first 5 alerts
    for opp in filtered[:5]:
        msg = format_alert_message(opp)
        await query.message.reply_text(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        await asyncio.sleep(0.3)

    # Show "more" button if needed
    if len(filtered) > 5:
        remaining = len(filtered) - 5
        last_scan_index = 5
        keyboard = [[InlineKeyboardButton(f"📋 Show More ({remaining} remaining)", callback_data="show_more")]]
        await query.message.reply_text(
            f"Showing 5 of {len(filtered)} results",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )


async def custom_ev_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom EV selection."""
    query = update.callback_query
    await query.answer()

    min_ev = int(query.data.replace("customev_", ""))
    chat_id = query.message.chat_id

    custom_scan_state[chat_id] = {'min_ev': min_ev}

    keyboard = [
        [
            InlineKeyboardButton(">0", callback_data=f"customkelly_{min_ev}_0"),
            InlineKeyboardButton("0.05", callback_data=f"customkelly_{min_ev}_0.05"),
            InlineKeyboardButton("0.15", callback_data=f"customkelly_{min_ev}_0.15"),
        ],
        [
            InlineKeyboardButton("0.30", callback_data=f"customkelly_{min_ev}_0.30"),
            InlineKeyboardButton("0.50", callback_data=f"customkelly_{min_ev}_0.50"),
            InlineKeyboardButton("0.75", callback_data=f"customkelly_{min_ev}_0.75"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.reply_text(
        f"🔒 <b>Custom Scan</b>\n\n"
        f"✅ Min EV: {min_ev}%\n\n"
        f"Step 2/3: Select minimum Kelly:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def custom_kelly_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom Kelly selection."""
    query = update.callback_query
    await query.answer()

    parts = query.data.replace("customkelly_", "").split("_")
    min_ev = int(parts[0])
    min_kelly = float(parts[1])

    chat_id = query.message.chat_id
    custom_scan_state[chat_id] = {'min_ev': min_ev, 'min_kelly': min_kelly}

    keyboard = [
        [
            InlineKeyboardButton("+100", callback_data=f"customodds_{min_ev}_{min_kelly}_100"),
            InlineKeyboardButton("+200", callback_data=f"customodds_{min_ev}_{min_kelly}_200"),
            InlineKeyboardButton("+300", callback_data=f"customodds_{min_ev}_{min_kelly}_300"),
        ],
        [
            InlineKeyboardButton("+500", callback_data=f"customodds_{min_ev}_{min_kelly}_500"),
            InlineKeyboardButton("+1000", callback_data=f"customodds_{min_ev}_{min_kelly}_1000"),
            InlineKeyboardButton("Any", callback_data=f"customodds_{min_ev}_{min_kelly}_-1000"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.reply_text(
        f"🔒 <b>Custom Scan</b>\n\n"
        f"✅ Min EV: {min_ev}%\n"
        f"✅ Min Kelly: {min_kelly}\n\n"
        f"Step 3/3: Select minimum odds:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def custom_odds_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom odds selection and run scan."""
    global last_scan_results, last_scan_index

    query = update.callback_query
    await query.answer()

    parts = query.data.replace("customodds_", "").split("_")
    min_ev = int(parts[0])
    min_kelly = float(parts[1])
    min_odds = int(parts[2])

    await query.message.reply_text(
        f"🔄 Running custom scan...\n"
        f"EV ≥{min_ev}% | Kelly ≥{min_kelly} | Odds ≥{min_odds:+d}",
        parse_mode=ParseMode.HTML
    )

    # Run scan
    opportunities = run_full_scan()

    # Apply custom filters
    filtered = [
        o for o in opportunities
        if o['ev'] >= min_ev
        and o['kelly'] >= min_kelly
        and o['best_odds'] >= min_odds
    ]

    if not filtered:
        await query.message.reply_text("❌ No opportunities match your criteria.", parse_mode=ParseMode.HTML)
        return

    await query.message.reply_text(
        f"✅ Found {len(filtered)} opportunities matching:\n"
        f"EV ≥{min_ev}% | Kelly ≥{min_kelly} | Odds ≥{min_odds:+d}",
        parse_mode=ParseMode.HTML
    )

    # Store for pagination
    last_scan_results = filtered
    last_scan_index = 0

    # Send first 5
    for opp in filtered[:5]:
        msg = format_alert_message(opp)
        await query.message.reply_text(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        await asyncio.sleep(0.3)

    if len(filtered) > 5:
        remaining = len(filtered) - 5
        last_scan_index = 5
        keyboard = [[InlineKeyboardButton(f"📋 Show More ({remaining} remaining)", callback_data="show_more")]]
        await query.message.reply_text(
            f"Showing 5 of {len(filtered)} results",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )


async def show_more_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle show more button."""
    global last_scan_index

    query = update.callback_query
    await query.answer()

    if not last_scan_results:
        await query.message.reply_text("No more results.", parse_mode=ParseMode.HTML)
        return

    # Send next 10
    end_index = min(last_scan_index + 10, len(last_scan_results))

    for opp in last_scan_results[last_scan_index:end_index]:
        msg = format_alert_message(opp)
        await query.message.reply_text(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        await asyncio.sleep(0.3)

    last_scan_index = end_index

    if last_scan_index < len(last_scan_results):
        remaining = len(last_scan_results) - last_scan_index
        keyboard = [[InlineKeyboardButton(f"📋 Show More ({remaining} remaining)", callback_data="show_more")]]
        await query.message.reply_text(
            f"Showing {last_scan_index} of {len(last_scan_results)} results",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    else:
        await query.message.reply_text(f"✅ All {len(last_scan_results)} results shown.", parse_mode=ParseMode.HTML)


async def book_scan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle book-specific scan."""
    global last_scan_results, last_scan_index

    query = update.callback_query
    await query.answer()

    # Parse: bookscan_DK_FIRE
    parts = query.data.replace("bookscan_", "").split("_")
    book_abbrev = parts[0]
    tier = parts[1] if len(parts) > 1 else 'ALL'

    book_name = BOOK_CONFIG.get(ABBREV_TO_BOOK.get(book_abbrev, ''), {}).get('name', book_abbrev)

    await query.message.reply_text(f"🔄 Scanning {book_name}...", parse_mode=ParseMode.HTML)

    # Run scan with book filter
    opportunities = run_full_scan(book_filter=book_abbrev)

    if not opportunities:
        await query.message.reply_text(f"❌ No opportunities found for {book_name}.", parse_mode=ParseMode.HTML)
        return

    # Filter by tier
    if tier != 'ALL' and tier != 'CUSTOM':
        filtered = [o for o in opportunities if o.get('tier') == tier]
    else:
        filtered = opportunities

    if not filtered:
        await query.message.reply_text(f"No {tier} alerts found for {book_name}.", parse_mode=ParseMode.HTML)
        return

    await query.message.reply_text(
        f"✅ Found {len(filtered)} opportunities for {book_name}",
        parse_mode=ParseMode.HTML
    )

    # Store and send
    last_scan_results = filtered
    last_scan_index = 0

    for opp in filtered[:5]:
        msg = format_alert_message(opp)
        await query.message.reply_text(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        await asyncio.sleep(0.3)

    if len(filtered) > 5:
        remaining = len(filtered) - 5
        last_scan_index = 5
        keyboard = [[InlineKeyboardButton(f"📋 Show More ({remaining} remaining)", callback_data="show_more")]]
        await query.message.reply_text(
            f"Showing 5 of {len(filtered)} results",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generic button callback router."""
    query = update.callback_query
    data = query.data

    if data == "status":
        await query.answer()
        await status_command(update, context)
    elif data == "settings":
        await query.answer()
        msg = (
            "⚙️ <b>Settings</b>\n\n"
            f"📍 State: {current_state.upper()}\n"
            f"🔄 Auto-scan: {'Enabled' if auto_scan_enabled else 'Disabled'}\n"
            f"⏱️ Interval: {SCAN_INTERVAL_SECONDS}s\n\n"
            "Commands:\n"
            "/setstate XX - Change state\n"
            "/toggle - Toggle auto-scan"
        )
        await query.message.reply_text(msg, parse_mode=ParseMode.HTML)
    elif data == "help":
        await query.answer()
        await help_command(update, context)


# =============================================================================
# WEBSOCKET HANDLERS
# =============================================================================

def handle_odds_update(data):
    """Handle real-time odds update from Pusher."""
    global updates_received, events_cache

    updates_received += 1
    timestamp = datetime.now().strftime('%H:%M:%S')

    try:
        if isinstance(data, str):
            changed_events = json.loads(data)
        else:
            changed_events = data

        event_ids = [e.get('eventID') for e in changed_events if e.get('eventID')]

        logger.info(f"[UPDATE #{updates_received}] {len(event_ids)} event(s) changed @ {timestamp}")

        if not event_ids:
            return

        start = time.time()
        events = fetch_events(event_ids)
        fetch_time = (time.time() - start) * 1000

        logger.info(f"   Fetched {len(events)} events in {fetch_time:.0f}ms")

        all_opportunities = []

        for event in events:
            event_id = event.get('eventID')
            events_cache[event_id] = event

            opps = scan_event_for_opportunities(event)
            tiered_opps = [o for o in opps if o.get('tier')]

            if tiered_opps:
                game = get_event_title(event)
                logger.info(f"   {game}: {len(tiered_opps)} tiered opportunities")
                all_opportunities.extend(tiered_opps)

        # Send alerts for new opportunities
        alerts_sent = 0
        for opp in all_opportunities:
            alert_key = generate_alert_key(
                opp['player'], opp['stat'], str(opp['line']), opp['side'], opp['best_book']
            )

            if should_send_alert(alert_key, opp['ev']):
                msg = format_alert_message(opp)
                send_telegram_message(msg)

                sent_alerts[alert_key] = {
                    'ev_pct': opp['ev'],
                    'timestamp': datetime.now(timezone.utc)
                }
                alerts_sent += 1
                time.sleep(0.5)

        if alerts_sent > 0:
            logger.info(f"   Sent {alerts_sent} alerts to Telegram")

    except Exception as e:
        logger.error(f"Error handling update: {e}", exc_info=True)


def send_telegram_message(text: str):
    """Send message to Telegram (sync)."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True,
        }
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            logger.error(f"Telegram error: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Telegram error: {e}")


def on_pusher_connect(data):
    logger.info(f"[CONNECTED] Pusher connection established")


def on_pusher_error(data):
    logger.error(f"[ERROR] Pusher error: {data}")


# =============================================================================
# SCHEDULED POLLING (REST MODE)
# =============================================================================

async def scheduled_poll(context: ContextTypes.DEFAULT_TYPE):
    """Poll for odds updates on a schedule."""
    global events_cache, updates_received

    if not auto_scan_enabled:
        return

    if not is_active_hours():
        return

    updates_received += 1
    logger.info(f"[POLL #{updates_received}] Fetching fresh odds...")

    try:
        # Fetch fresh events
        start = time.time()
        events = fetch_events()
        fetch_time = (time.time() - start) * 1000

        if not events:
            logger.warning("No events returned from API")
            return

        logger.info(f"   Fetched {len(events)} events in {fetch_time:.0f}ms")

        # Update cache
        for event in events:
            event_id = event.get('eventID')
            events_cache[event_id] = event

        # Scan for opportunities
        all_opportunities = []
        for event in events:
            opps = scan_event_for_opportunities(event)
            tiered_opps = [o for o in opps if o.get('tier')]
            if tiered_opps:
                all_opportunities.extend(tiered_opps)

        logger.info(f"   Found {len(all_opportunities)} tiered opportunities")

        # Send alerts for new opportunities
        alerts_sent = 0
        for opp in all_opportunities:
            alert_key = generate_alert_key(
                opp['player'], opp['stat'], str(opp['line']), opp['side'], opp['best_book']
            )

            if should_send_alert(alert_key, opp['ev']):
                msg = format_alert_message(opp)
                send_telegram_message(msg)

                sent_alerts[alert_key] = {
                    'ev_pct': opp['ev'],
                    'timestamp': datetime.now(timezone.utc)
                }
                alerts_sent += 1
                await asyncio.sleep(0.5)

        if alerts_sent > 0:
            logger.info(f"   Sent {alerts_sent} new alerts to Telegram")

    except Exception as e:
        logger.error(f"Poll error: {e}", exc_info=True)


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Start the bot with REST polling."""
    global events_cache

    print("=" * 60)
    print("SportsGameOdds Bot (REST Polling Mode)")
    print("=" * 60)
    print(f"📡 API: {API_BASE_URL}")
    print(f"💬 Telegram: {TELEGRAM_CHAT_ID}")
    print(f"📍 State: {current_state.upper()}")
    print(f"⏱️ Poll Interval: {SCAN_INTERVAL_SECONDS}s")
    print("=" * 60)

    # Initial fetch
    logger.info("[INIT] Fetching initial events...")
    events = fetch_events()

    if not events:
        logger.error("Failed to fetch events")
        sys.exit(1)

    logger.info(f"[INIT] Found {len(events)} events:")
    for event in events:
        event_id = event.get('eventID')
        events_cache[event_id] = event
        logger.info(f"   - {get_event_title(event)}")

    # Initial scan
    logger.info("\n[SCAN] Running initial scan...")
    all_opps = run_full_scan()
    tiered_opps = [o for o in all_opps if o.get('tier')]
    logger.info(f"[SCAN] Found {len(tiered_opps)} tiered opportunities")

    # Send startup message
    startup_msg = (
        "🚀 <b>SGO Bot Started</b>\n\n"
        f"📡 Mode: REST Polling ({SCAN_INTERVAL_SECONDS}s)\n"
        f"🏀 Events: {len(events)}\n"
        f"🎯 Opportunities: {len(tiered_opps)}\n\n"
        "<i>Use /scan to view opportunities</i>\n"
        "<i>Auto-polling for new alerts...</i>"
    )
    send_telegram_message(startup_msg)

    # Build Telegram bot
    logger.info("\n[BOT] Starting Telegram bot...")
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("setstate", setstate_command))
    app.add_handler(CommandHandler("toggle", toggle_command))
    app.add_handler(CommandHandler("books", books_command))

    # Book commands
    app.add_handler(CommandHandler("dk", dk_command))
    app.add_handler(CommandHandler("fd", fd_command))
    app.add_handler(CommandHandler("mg", mg_command))
    app.add_handler(CommandHandler("cz", cz_command))
    app.add_handler(CommandHandler("es", es_command))
    app.add_handler(CommandHandler("fn", fn_command))
    app.add_handler(CommandHandler("br", br_command))
    app.add_handler(CommandHandler("bb", bb_command))
    app.add_handler(CommandHandler("fl", fl_command))

    # Callback handlers
    app.add_handler(CallbackQueryHandler(scan_callback, pattern="^scan_"))
    app.add_handler(CallbackQueryHandler(custom_ev_callback, pattern="^customev_"))
    app.add_handler(CallbackQueryHandler(custom_kelly_callback, pattern="^customkelly_"))
    app.add_handler(CallbackQueryHandler(custom_odds_callback, pattern="^customodds_"))
    app.add_handler(CallbackQueryHandler(show_more_callback, pattern="^show_more"))
    app.add_handler(CallbackQueryHandler(book_scan_callback, pattern="^bookscan_"))
    app.add_handler(CallbackQueryHandler(button_callback))

    # Schedule polling
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(
            scheduled_poll,
            interval=SCAN_INTERVAL_SECONDS,
            first=30  # First poll 30 seconds after start
        )
        logger.info(f"[POLL] Scheduled polling every {SCAN_INTERVAL_SECONDS}s")

    print("\n🚀 Bot running! Press Ctrl+C to stop\n")

    # Run bot
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
