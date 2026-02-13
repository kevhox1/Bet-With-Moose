"""
NBA Value Alert Bot - Main Telegram Bot with Scheduler
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

import pandas as pd
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

# Disable link previews globally for bet messages
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)

import config
import database
from nba_value_scanner import scan_for_opportunities, get_alerts, format_alert_message

# Import odds caching (optional)
try:
    import odds_cache
    CACHING_AVAILABLE = True
except ImportError:
    CACHING_AVAILABLE = False

# Import bet logger for ROI tracking
try:
    import bet_logger
    bet_logger.init_bet_log_database()
    BET_LOGGING_ENABLED = True
except ImportError:
    BET_LOGGING_ENABLED = False

# Import bet grader for auto-grading
try:
    import bet_grader
    BET_GRADING_ENABLED = True
except ImportError:
    BET_GRADING_ENABLED = False

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Eastern timezone
ET = pytz.timezone('US/Eastern')

# Global reference to application for rescheduling
app_reference = None

# Store pending alerts for "Show More" functionality
# Key: chat_id, Value: {'alerts': DataFrame, 'offset': int, 'state': str}
pending_alerts = {}


def get_scan_interval() -> int:
    """Get current scan interval from database or config default."""
    interval = database.get_setting('scan_interval')
    if interval:
        return int(interval)
    return config.SCAN_INTERVAL_SECONDS


def get_state() -> str:
    """Get current state from database or config default."""
    state = database.get_setting('state')
    if state:
        return state.lower()
    return config.STATE.lower()


def get_max_alerts(tier: str) -> int:
    """Get max alerts for a tier from database or config default."""
    max_val = database.get_setting(f'max_alerts_{tier.lower()}')
    if max_val:
        return int(max_val)
    return config.MAX_ALERTS_PER_TIER.get(tier, 0)


def get_legal_books(state: str) -> list:
    """Get list of legal sportsbooks for the given state."""
    return config.STATE_LEGAL_BOOKS.get(state.lower(), [])


def is_bet_available_in_state(best_books_str: str, state: str) -> bool:
    """
    Check if at least one of the best books is legal in the given state.
    Also excludes bets where ALL best books are in EXCLUDED_BOOKS (Pinnacle, Bovada).

    Args:
        best_books_str: Comma-separated string of book abbreviations (e.g., "DK, FD")
        state: State abbreviation

    Returns:
        True if at least one book is legal in the state and not excluded
    """
    legal_books = get_legal_books(state)
    if not legal_books:
        return False

    # Parse the best books string
    best_books = [b.strip() for b in best_books_str.split(',')]

    # Filter out excluded books (Pinnacle, Bovada)
    excluded = getattr(config, 'EXCLUDED_BOOKS', ['PN', 'BV'])
    available_books = [b for b in best_books if b not in excluded]

    # If all best books were excluded, this bet is not available
    if not available_books:
        return False

    # Check if any remaining best book is legal in the state
    return any(book in legal_books for book in available_books)


def get_available_book_for_bet(best_books_str: str, state: str) -> str:
    """
    Get the first legal book from the best books list for the state.
    Excludes Pinnacle and Bovada.

    Returns:
        Book abbreviation or None if no legal book available
    """
    legal_books = get_legal_books(state)
    best_books = [b.strip() for b in best_books_str.split(',')]
    excluded = getattr(config, 'EXCLUDED_BOOKS', ['PN', 'BV'])

    for book in best_books:
        if book in legal_books and book not in excluded:
            return book
    return None


def process_alerts_for_state(alerts_df, state: str, allowed_books: list = None):
    """
    Filter alerts to only those where a legal book in the state qualifies for any tier.

    For each alert, check if ANY legal book has odds that INDEPENDENTLY qualify for a tier.
    Uses pre-calculated per-book EV/Kelly metrics from the scanner.

    Args:
        alerts_df: DataFrame with all alerts
        state: State abbreviation
        allowed_books: Optional list of specific books to filter to (for auto-scan book selection)

    Returns:
        DataFrame with alerts available in the state
    """
    from nba_value_scanner import get_book_url

    available_rows = []
    excluded = getattr(config, 'EXCLUDED_BOOKS', ['PN', 'BV', 'BO'])
    legal_books = get_legal_books(state)

    # If allowed_books specified, further restrict legal_books
    if allowed_books:
        legal_books = [b for b in legal_books if b in allowed_books]

    for _, row in alerts_df.iterrows():
        qualifying_books = row.get('_qualifying_books', {})
        per_book_metrics = row.get('_per_book_metrics', {})

        # Find the best qualifying book that's legal in this state
        best_legal_book = None
        best_legal_metrics = None
        best_legal_tier = None

        # Check each tier (in order of priority: FIRE -> OUTLIER -> VALUE_LONGSHOT)
        for tier, books in qualifying_books.items():
            for book in books:
                if book in legal_books and book not in excluded:
                    metrics = per_book_metrics.get(book)
                    if metrics is not None:
                        # Take the book with best odds among qualifying legal books
                        if best_legal_metrics is None or metrics['odds'] > best_legal_metrics['odds']:
                            best_legal_book = book
                            best_legal_metrics = metrics
                            best_legal_tier = tier

        if best_legal_book and best_legal_metrics:
            # Found a qualifying legal book - use its pre-calculated metrics
            row_dict = row.to_dict()
            row_dict['Best Books'] = best_legal_book
            row_dict['Best Odds'] = best_legal_metrics['odds']
            row_dict['Alert Tier'] = best_legal_tier
            row_dict['EV %'] = best_legal_metrics['ev_pct']
            row_dict['Std. Recc. U'] = best_legal_metrics['kelly']
            row_dict['Conf. Adj. Recc. U'] = best_legal_metrics['conf_kelly']

            # Use API-provided deep link if available, fallback to generic URL
            api_link = best_legal_metrics.get('link', '')
            row_dict['_link'] = api_link if api_link else get_book_url(best_legal_book, state)
            available_rows.append(row_dict)

    if not available_rows:
        return pd.DataFrame()

    return pd.DataFrame(available_rows)


def is_active_hours() -> bool:
    """Check if current time is within active betting hours."""
    now_et = datetime.now(ET)
    hour = now_et.hour

    # Handle overnight range (e.g., 6 PM to 1 AM)
    if config.ACTIVE_HOURS_START > config.ACTIVE_HOURS_END:
        return hour >= config.ACTIVE_HOURS_START or hour < config.ACTIVE_HOURS_END
    else:
        return config.ACTIVE_HOURS_START <= hour < config.ACTIVE_HOURS_END


def is_paused() -> bool:
    """Check if automatic alerts are paused."""
    return database.get_setting('paused', 'false') == 'true'


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    interval = get_scan_interval() // 60
    current_state = get_state()
    legal_books = get_legal_books(current_state)

    welcome_msg = f"""
🏀 <b>NBA Value Alert Bot</b>

I scan NBA player props for +EV betting opportunities and send you alerts!

<b>Commands:</b>
/scan - Run manual scan (shows all tiers)
/status - Bot status and stats
/settings - View current settings
/books - View legal sportsbooks for your state
/pause - Pause automatic alerts
/resume - Resume automatic alerts

<b>Per-Book Scans:</b>
/dk /fd /mg /cz /es /fn /br /bp /rk /bb /ci /rb /fl

<b>Configuration:</b>
/setinterval [minutes] - Set scan frequency
/setstate [state] - Set state for bet links
/setmax [tier] [count] - Set max alerts per tier

<b>Alert Tiers:</b>
🔥 FIRE - High confidence (Kelly ≥0.3, Cov ≥8)
🎯 VALUE_LONGSHOT - Long odds value (+500, Kelly ≥0.15)
⚡ OUTLIER - Market outlier (35%+ vs next, Cov ≥3)

<b>Current State:</b> {current_state.upper()} ({len(legal_books)} legal books)

Automatic scans run every {interval} minutes.
Only bets available at legal sportsbooks in your state are sent.
"""
    await update.message.reply_text(welcome_msg, parse_mode=ParseMode.HTML)


async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /scan command - show tier selection buttons."""
    current_state = get_state()
    legal_books = get_legal_books(current_state)

    # Show tier selection buttons
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
        f"📚 {len(legal_books)} legal books\n\n"
        f"Select tier filter:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def scan_tier_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle scan tier selection callback."""
    query = update.callback_query
    await query.answer()

    # Parse tier from callback data: scantier_FIRE
    tier = query.data.split("_")[1]
    chat_id = update.effective_chat.id
    current_state = get_state()

    # Handle CUSTOM tier - show EV selection
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

    # Run the scan
    await run_manual_scan(query, context, tier, chat_id, current_state)


async def scan_custom_ev_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle scan custom EV selection."""
    query = update.callback_query
    await query.answer()

    # Parse: scancustomev_10
    min_ev = int(query.data.split("_")[1])
    current_state = get_state()

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
        f"🔍 <b>Manual Scan</b> ({current_state.upper()})\n\n"
        f"🔒 Custom - EV≥{min_ev}%\n"
        f"Select min Kelly:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def scan_custom_kelly_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle scan custom Kelly selection - shows odds selection."""
    query = update.callback_query
    await query.answer()

    # Parse: scancustomkelly_10_0.5
    parts = query.data.split("_")
    min_ev = int(parts[1])
    min_kelly = float(parts[2])
    current_state = get_state()

    keyboard = [
        [
            InlineKeyboardButton("+100", callback_data=f"scancustomodds_{min_ev}_{min_kelly}_100"),
            InlineKeyboardButton("+200", callback_data=f"scancustomodds_{min_ev}_{min_kelly}_200"),
            InlineKeyboardButton("+300", callback_data=f"scancustomodds_{min_ev}_{min_kelly}_300"),
            InlineKeyboardButton("+500", callback_data=f"scancustomodds_{min_ev}_{min_kelly}_500"),
        ],
        [
            InlineKeyboardButton("+750", callback_data=f"scancustomodds_{min_ev}_{min_kelly}_750"),
            InlineKeyboardButton("+1000", callback_data=f"scancustomodds_{min_ev}_{min_kelly}_1000"),
            InlineKeyboardButton("+1500", callback_data=f"scancustomodds_{min_ev}_{min_kelly}_1500"),
            InlineKeyboardButton("+2000", callback_data=f"scancustomodds_{min_ev}_{min_kelly}_2000"),
        ],
        [
            InlineKeyboardButton("+2500", callback_data=f"scancustomodds_{min_ev}_{min_kelly}_2500"),
            InlineKeyboardButton("+3000", callback_data=f"scancustomodds_{min_ev}_{min_kelly}_3000"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"🔍 <b>Manual Scan</b> ({current_state.upper()})\n\n"
        f"🔒 Custom Filter\n"
        f"✅ EV ≥ {min_ev}%\n"
        f"✅ Kelly ≥ {min_kelly}\n\n"
        f"Select minimum odds:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def scan_custom_odds_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle scan custom odds selection - runs the scan."""
    query = update.callback_query
    await query.answer()

    # Parse: scancustomodds_10_0.5_500
    parts = query.data.split("_")
    min_ev = int(parts[1])
    min_kelly = float(parts[2])
    min_odds = int(parts[3])

    chat_id = update.effective_chat.id
    current_state = get_state()

    # Run scan with custom filter
    await run_manual_scan(query, context, "CUSTOM", chat_id, current_state, min_ev, min_kelly, min_odds)


async def run_manual_scan(query, context, tier: str, chat_id: int, current_state: str, min_ev: float = None, min_kelly: float = None, min_odds: int = None):
    """Execute the manual scan with the selected tier/custom filter."""
    tier_labels = {'FIRE': '🔥 Fire', 'VALUE_LONGSHOT': '🎯 Longshot', 'OUTLIER': '⚡ Outlier', 'ALL': '📊 All', 'CUSTOM': '🔒 Custom'}
    tier_label = tier_labels.get(tier, tier)
    legal_books = get_legal_books(current_state)

    if tier == "CUSTOM":
        filter_text = f"🔒 EV≥{min_ev}%, Kelly≥{min_kelly}, Odds≥+{min_odds}"
    else:
        filter_text = f"Tier: {tier_label}"

    await query.edit_message_text(
        f"🔄 Scanning NBA odds for <b>{current_state.upper()}</b>...\n"
        f"📚 Filtering for: {', '.join(legal_books)}\n"
        f"📋 {filter_text}",
        parse_mode=ParseMode.HTML
    )

    try:
        df, api_remaining = scan_for_opportunities(state=current_state, verbose=False)

        # Store API quota in database for status command
        if api_remaining:
            database.set_setting('api_remaining', api_remaining)

        if df.empty:
            remaining_msg = f"\n🔑 API Quota: {api_remaining} requests remaining" if api_remaining else ""
            await context.bot.send_message(chat_id=chat_id, text=f"No opportunities found. Markets may be closed.{remaining_msg}")
            return

        all_alerts = get_alerts(df)

        if all_alerts.empty:
            await context.bot.send_message(chat_id=chat_id, text="No alerts meet the thresholds right now.")
            return

        # Filter by tier
        if tier == "CUSTOM":
            alerts = all_alerts[
                (all_alerts['EV %'] >= min_ev) &
                (all_alerts['Std. Recc. U'] >= min_kelly) &
                (all_alerts['Best Odds'] >= min_odds)
            ]
        elif tier == "ALL":
            alerts = all_alerts
        else:
            alerts = all_alerts[all_alerts['Alert Tier'] == tier]

        if alerts.empty:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"No {tier_label} alerts found. Total alerts: {len(all_alerts)}",
                parse_mode=ParseMode.HTML
            )
            return

        # Process alerts - find available bets, with fallback to next-best legal book
        available_alerts = process_alerts_for_state(alerts, current_state)

        if available_alerts.empty:
            total_found = len(alerts)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Found {total_found} alerts, but none are available on legal books in {current_state.upper()}.\n"
                     f"Try /books to see which sportsbooks are available in your state.",
                parse_mode=ParseMode.HTML
            )
            return

        # Count totals
        total_alerts = len(available_alerts)
        total_before = len(alerts)
        filtered_out = total_before - total_alerts

        # Send summary
        summary = f"📊 <b>Scan Complete ({current_state.upper()} - {tier_label})</b>\n"
        if tier == "CUSTOM":
            summary += f"Filter: EV≥{min_ev}%, Kelly≥{min_kelly}, Odds≥+{min_odds}\n"
        summary += f"Found {total_alerts} alerts"
        if filtered_out > 0:
            summary += f"\n⚠️ {filtered_out} filtered (not in {current_state.upper()})"
        if api_remaining:
            summary += f"\n🔑 API Quota: {api_remaining} remaining"
        await context.bot.send_message(chat_id=chat_id, text=summary, parse_mode=ParseMode.HTML)

        # Send first batch of alerts (5 at a time)
        BATCH_SIZE = 5
        sent_count = 0

        for i, (_, row) in enumerate(available_alerts.iterrows()):
            if i >= BATCH_SIZE:
                break

            unique_key = f"{row['Player']}|{row['Market']}|{row['Side']}|{row['Line']}"
            msg = format_alert_message(row)

            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML, link_preview_options=NO_PREVIEW)
            sent_count += 1

            # Record in database (manual scans bypass duplicate check intentionally)
            database.record_sent_alert(
                unique_key=unique_key,
                best_odds=int(row['Best Odds']),
                ev_percent=row['EV %'],
                tier=row['Alert Tier'],
                game_datetime=row.get('Game Datetime'),
                best_book=row.get('Best Books', '').split(',')[0].strip() if row.get('Best Books') else None
            )

            await asyncio.sleep(0.3)

        # If there are more alerts, store them and show "Show More" button
        remaining = total_alerts - BATCH_SIZE
        if remaining > 0:
            # Store remaining alerts for this chat
            pending_alerts[chat_id] = {
                'alerts': available_alerts,
                'offset': sent_count,
                'state': current_state
            }

            # Create "Show More" button
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
    await query.answer()  # Acknowledge the button press

    chat_id = update.effective_chat.id

    # Check if we have pending alerts for this chat
    if chat_id not in pending_alerts:
        await query.edit_message_text("⚠️ No more alerts available. Run /scan again.")
        return

    data = pending_alerts[chat_id]
    alerts_df = data['alerts']
    offset = data['offset']
    current_state = data['state']
    total_alerts = len(alerts_df)

    # Update the old button message to show it was used
    await query.edit_message_text(
        f"📊 Showed {offset}/{total_alerts} alerts",
        parse_mode=ParseMode.HTML
    )

    # Send next batch
    BATCH_SIZE = 5
    sent_count = 0

    for i in range(offset, min(offset + BATCH_SIZE, total_alerts)):
        row = alerts_df.iloc[i]
        unique_key = f"{row['Player']}|{row['Market']}|{row['Side']}|{row['Line']}"
        msg = format_alert_message(row)

        await context.bot.send_message(
            chat_id=chat_id,
            text=msg,
            parse_mode=ParseMode.HTML,
            link_preview_options=NO_PREVIEW
        )
        sent_count += 1

        # Record in database (manual scans bypass duplicate check intentionally)
        database.record_sent_alert(
            unique_key=unique_key,
            best_odds=int(row['Best Odds']),
            ev_percent=row['EV %'],
            tier=row['Alert Tier'],
            game_datetime=row.get('Game Datetime'),
            best_book=row.get('Best Books', '').split(',')[0].strip() if row.get('Best Books') else None
        )

        await asyncio.sleep(0.3)

    # Update offset
    new_offset = offset + sent_count
    remaining = total_alerts - new_offset

    if remaining > 0:
        # Update stored offset
        pending_alerts[chat_id]['offset'] = new_offset

        # Send NEW message with button at the bottom
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
        # No more alerts, remove from pending and send completion message
        del pending_alerts[chat_id]
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ All {total_alerts} alerts shown",
            parse_mode=ParseMode.HTML
        )


# Book abbreviation to full name mapping for per-book scans
BOOK_SCAN_MAP = {
    'dk': ('DK', 'DraftKings'),
    'fd': ('FD', 'FanDuel'),
    'mg': ('MG', 'BetMGM'),
    'cz': ('CZ', 'Caesars'),
    'es': ('ES', 'ESPN Bet'),
    'fn': ('FN', 'Fanatics'),
    'br': ('BR', 'BetRivers'),
    'bp': ('BP', 'BetParx'),
}


async def book_scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE, book_abbrev: str, book_name: str):
    """Generic handler for per-book scan commands - shows tier selection buttons."""
    current_state = get_state()

    # Show tier selection buttons
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
        f"📚 <b>{book_name} Scan</b> ({current_state.upper()})\n\n"
        f"Select tier filter:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def book_tier_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle book tier selection callback."""
    query = update.callback_query
    await query.answer()

    # Parse book and tier from callback data: booktier_DK_FIRE
    parts = query.data.split("_")
    book_abbrev = parts[1]
    tier = parts[2]

    book_name = config.BOOK_FULL_NAMES.get(book_abbrev, book_abbrev)
    chat_id = update.effective_chat.id
    current_state = get_state()

    # Handle CUSTOM tier - show EV selection
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

    # Run the scan
    await run_book_scan(query, context, book_abbrev, book_name, tier, chat_id, current_state)


async def book_custom_ev_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle book custom EV selection."""
    query = update.callback_query
    await query.answer()

    # Parse: bookcustomev_DK_10
    parts = query.data.split("_")
    book_abbrev = parts[1]
    min_ev = int(parts[2])

    book_name = config.BOOK_FULL_NAMES.get(book_abbrev, book_abbrev)

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
    """Handle book custom Kelly selection - shows odds selection."""
    query = update.callback_query
    await query.answer()

    # Parse: bookcustomkelly_DK_10_0.5
    parts = query.data.split("_")
    book_abbrev = parts[1]
    min_ev = int(parts[2])
    min_kelly = float(parts[3])

    book_name = config.BOOK_FULL_NAMES.get(book_abbrev, book_abbrev)

    # Show min odds selection buttons
    keyboard = [
        [
            InlineKeyboardButton("+100", callback_data=f"bookcustomodds_{book_abbrev}_{min_ev}_{min_kelly}_100"),
            InlineKeyboardButton("+200", callback_data=f"bookcustomodds_{book_abbrev}_{min_ev}_{min_kelly}_200"),
            InlineKeyboardButton("+300", callback_data=f"bookcustomodds_{book_abbrev}_{min_ev}_{min_kelly}_300"),
            InlineKeyboardButton("+500", callback_data=f"bookcustomodds_{book_abbrev}_{min_ev}_{min_kelly}_500"),
        ],
        [
            InlineKeyboardButton("+750", callback_data=f"bookcustomodds_{book_abbrev}_{min_ev}_{min_kelly}_750"),
            InlineKeyboardButton("+1000", callback_data=f"bookcustomodds_{book_abbrev}_{min_ev}_{min_kelly}_1000"),
            InlineKeyboardButton("+1500", callback_data=f"bookcustomodds_{book_abbrev}_{min_ev}_{min_kelly}_1500"),
            InlineKeyboardButton("+2000", callback_data=f"bookcustomodds_{book_abbrev}_{min_ev}_{min_kelly}_2000"),
        ],
        [
            InlineKeyboardButton("+2500", callback_data=f"bookcustomodds_{book_abbrev}_{min_ev}_{min_kelly}_2500"),
            InlineKeyboardButton("+3000", callback_data=f"bookcustomodds_{book_abbrev}_{min_ev}_{min_kelly}_3000"),
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
    """Handle book custom odds selection - runs the scan."""
    query = update.callback_query
    await query.answer()

    # Parse: bookcustomodds_DK_10_0.5_500
    parts = query.data.split("_")
    book_abbrev = parts[1]
    min_ev = int(parts[2])
    min_kelly = float(parts[3])
    min_odds = int(parts[4])

    book_name = config.BOOK_FULL_NAMES.get(book_abbrev, book_abbrev)
    chat_id = update.effective_chat.id
    current_state = get_state()

    # Run scan with custom filter including min_odds
    await run_book_scan(query, context, book_abbrev, book_name, "CUSTOM", chat_id, current_state, min_ev, min_kelly, min_odds)


async def run_book_scan(query, context, book_abbrev: str, book_name: str, tier: str, chat_id: int, current_state: str, min_ev: float = None, min_kelly: float = None, min_odds: int = None):
    """Execute the book scan with the selected tier/custom filter."""
    tier_labels = {'FIRE': '🔥', 'VALUE_LONGSHOT': '🎯', 'OUTLIER': '⚡', 'ALL': 'All', 'CUSTOM': '🔒'}
    tier_label = tier_labels.get(tier, tier)

    if tier == "CUSTOM":
        filter_text = f"🔒 EV≥{min_ev}%, Kelly≥{min_kelly}, Odds≥+{min_odds}"
    else:
        filter_text = f"Tier: {tier_label}"

    await query.edit_message_text(
        f"🔄 Scanning <b>{book_name}</b>...\n"
        f"📍 State: {current_state.upper()}\n"
        f"📋 {filter_text}",
        parse_mode=ParseMode.HTML
    )

    try:
        df, api_remaining = scan_for_opportunities(state=current_state, verbose=False)

        if api_remaining:
            database.set_setting('api_remaining', api_remaining)

        if df.empty:
            await context.bot.send_message(chat_id=chat_id, text="No opportunities found. Markets may be closed.")
            return

        all_alerts = get_alerts(df)

        if all_alerts.empty:
            await context.bot.send_message(chat_id=chat_id, text="No alerts meet the thresholds right now.")
            return

        # Filter by tier
        if tier == "CUSTOM":
            alerts = all_alerts[
                (all_alerts['EV %'] >= min_ev) &
                (all_alerts['Std. Recc. U'] >= min_kelly) &
                (all_alerts['Best Odds'] >= min_odds)
            ]
        elif tier == "ALL":
            alerts = all_alerts
        else:
            alerts = all_alerts[all_alerts['Alert Tier'] == tier]

        # Filter to only show bets where the specified book has the best odds
        book_alerts = alerts[
            alerts['Best Books'].str.contains(book_abbrev, case=False, na=False)
        ].reset_index(drop=True)

        if book_alerts.empty:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"No {tier_label} alerts with best odds on {book_name}.\nTotal alerts: {len(all_alerts)}",
                parse_mode=ParseMode.HTML
            )
            return

        # Send summary
        total = len(book_alerts)
        summary = f"📊 <b>{book_name} - {tier_label}</b>\n"
        if tier == "CUSTOM":
            summary += f"Filter: EV≥{min_ev}%, Kelly≥{min_kelly}, Odds≥+{min_odds}\n"
        summary += f"Found {total} alerts"
        if api_remaining:
            summary += f"\n🔑 API: {api_remaining} remaining"
        await context.bot.send_message(chat_id=chat_id, text=summary, parse_mode=ParseMode.HTML)

        # Send first 10 alerts
        BATCH_SIZE = 10
        sent_count = 0
        for i, (_, row) in enumerate(book_alerts.iterrows()):
            if i >= BATCH_SIZE:
                break
            msg = format_alert_message(row)
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML, link_preview_options=NO_PREVIEW)
            sent_count += 1
            await asyncio.sleep(0.3)

        # Show "Show 10 More" button if there are more alerts
        remaining = total - sent_count
        if remaining > 0:
            pending_alerts[f"book_{chat_id}"] = {
                'alerts': book_alerts,
                'offset': sent_count,
                'book_abbrev': book_abbrev,
                'book_name': book_name
            }
            keyboard = [[InlineKeyboardButton(f"📋 Show 10 More ({remaining} remaining)", callback_data=f"bookmore_{book_abbrev}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"📊 Showing {sent_count}/{total} alerts",
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )

    except Exception as e:
        logger.error(f"Error in {book_name} scan: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Scan error: {str(e)}")


async def book_show_more_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'Show 10 More' button callback for per-book scans."""
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    book_key = f"book_{chat_id}"

    # Check if we have pending alerts for this chat
    if book_key not in pending_alerts:
        await query.edit_message_text("⚠️ No more alerts available. Run the book scan again.")
        return

    data = pending_alerts[book_key]
    alerts_df = data['alerts']
    offset = data['offset']
    book_name = data['book_name']
    book_abbrev = data['book_abbrev']
    total_alerts = len(alerts_df)

    # Update the old button message to show it was used
    await query.edit_message_text(
        f"📊 Showed {offset}/{total_alerts} {book_name} alerts",
        parse_mode=ParseMode.HTML
    )

    # Send next batch of 10
    BATCH_SIZE = 10
    sent_count = 0

    for i in range(offset, min(offset + BATCH_SIZE, total_alerts)):
        row = alerts_df.iloc[i]
        msg = format_alert_message(row)
        await context.bot.send_message(
            chat_id=chat_id,
            text=msg,
            parse_mode=ParseMode.HTML,
            link_preview_options=NO_PREVIEW
        )
        sent_count += 1
        await asyncio.sleep(0.3)

    # Update offset
    new_offset = offset + sent_count
    remaining = total_alerts - new_offset

    if remaining > 0:
        # Update stored offset
        pending_alerts[book_key]['offset'] = new_offset

        # Send NEW message with button at the bottom
        keyboard = [[InlineKeyboardButton(f"📋 Show 10 More ({remaining} remaining)", callback_data=f"bookmore_{book_abbrev}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"📊 Showing {new_offset}/{total_alerts} {book_name} alerts",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    else:
        # No more alerts, remove from pending and send completion message
        del pending_alerts[book_key]
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ All {total_alerts} {book_name} alerts shown",
            parse_mode=ParseMode.HTML
        )


# Create individual command handlers for each book
async def dk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan for DraftKings bets."""
    await book_scan_command(update, context, 'DK', 'DraftKings')

async def fd_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan for FanDuel bets."""
    await book_scan_command(update, context, 'FD', 'FanDuel')

async def mg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan for BetMGM bets."""
    await book_scan_command(update, context, 'MG', 'BetMGM')

async def cz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan for Caesars bets."""
    await book_scan_command(update, context, 'CZ', 'Caesars')

async def es_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan for ESPN Bet bets."""
    await book_scan_command(update, context, 'ES', 'ESPN Bet')

async def fn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan for Fanatics bets."""
    await book_scan_command(update, context, 'FN', 'Fanatics')

async def br_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan for BetRivers bets."""
    await book_scan_command(update, context, 'BR', 'BetRivers')

async def bp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan for BetParx bets."""
    await book_scan_command(update, context, 'BP', 'BetParx')

async def rk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan for Hard Rock bets."""
    await book_scan_command(update, context, 'RK', 'Hard Rock')

async def bb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan for Bally Bet bets."""
    await book_scan_command(update, context, 'BB', 'Bally Bet')

async def ci_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan for Circa bets."""
    await book_scan_command(update, context, 'CI', 'Circa')

async def rb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan for Rebet bets."""
    await book_scan_command(update, context, 'RB', 'Rebet')

async def fl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan for Fliff bets."""
    await book_scan_command(update, context, 'FL', 'Fliff')


async def state_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /state command - State-specific scan with tier filter buttons."""
    # Check if state is provided as argument
    if context.args:
        state = context.args[0].lower()
        if state not in config.VALID_STATES:
            states_list = ', '.join(config.VALID_STATES).upper()
            await update.message.reply_text(
                f"❌ Invalid state: {state.upper()}\n\n"
                f"Valid states: {states_list}",
                parse_mode=ParseMode.HTML
            )
            return
    else:
        state = get_state()

    # Store state for callback
    chat_id = update.effective_chat.id
    pending_alerts[f"state_scan_{chat_id}"] = {'state': state}

    # Show tier selection buttons
    keyboard = [
        [
            InlineKeyboardButton("🔥 Fire", callback_data=f"statetier_{state}_FIRE"),
            InlineKeyboardButton("🎯 Longshot", callback_data=f"statetier_{state}_VALUE_LONGSHOT"),
            InlineKeyboardButton("⚡ Outlier", callback_data=f"statetier_{state}_OUTLIER"),
        ],
        [
            InlineKeyboardButton("📊 All", callback_data=f"statetier_{state}_ALL"),
            InlineKeyboardButton("🔒 Custom", callback_data=f"statetier_{state}_CUSTOM"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    legal_books = get_legal_books(state)
    await update.message.reply_text(
        f"📍 <b>Scan for {state.upper()}</b> ({len(legal_books)} legal books)\n\n"
        f"Select alert tier filter:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def state_tier_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle state tier selection callback - runs the scan with selected tier."""
    query = update.callback_query
    await query.answer()

    # Parse state and tier from callback data: statetier_nj_FIRE
    parts = query.data.split("_")
    state = parts[1]
    tier = parts[2]

    chat_id = update.effective_chat.id
    legal_books = get_legal_books(state)

    # Handle CUSTOM tier - show EV selection
    if tier == "CUSTOM":
        keyboard = [
            [
                InlineKeyboardButton("EV≥5%", callback_data=f"statecustomev_{state}_5"),
                InlineKeyboardButton("EV≥10%", callback_data=f"statecustomev_{state}_10"),
                InlineKeyboardButton("EV≥15%", callback_data=f"statecustomev_{state}_15"),
            ],
            [
                InlineKeyboardButton("EV≥20%", callback_data=f"statecustomev_{state}_20"),
                InlineKeyboardButton("EV≥25%", callback_data=f"statecustomev_{state}_25"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"📍 <b>Scan for {state.upper()}</b>\n\n"
            f"🔒 <b>Custom Filter - Step 1</b>\n\n"
            f"Select minimum EV%:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        return

    await query.edit_message_text(
        f"🔄 Scanning for <b>{state.upper()}</b>...\n"
        f"📚 Books: {', '.join(legal_books)}\n"
        f"📋 Tier: {tier if tier != 'ALL' else 'All tiers'}",
        parse_mode=ParseMode.HTML
    )

    try:
        df, api_remaining = scan_for_opportunities(state=state, verbose=False)

        if api_remaining:
            database.set_setting('api_remaining', api_remaining)

        if df.empty:
            await context.bot.send_message(
                chat_id=chat_id,
                text="No opportunities found. Markets may be closed.",
                parse_mode=ParseMode.HTML
            )
            return

        all_alerts = get_alerts(df)

        if all_alerts.empty:
            await context.bot.send_message(
                chat_id=chat_id,
                text="No alerts meet the thresholds right now.",
                parse_mode=ParseMode.HTML
            )
            return

        # Filter by tier
        if tier == "ALL":
            alerts = all_alerts
        else:
            alerts = all_alerts[all_alerts['Alert Tier'] == tier]

        if alerts.empty:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"No {tier} alerts found. Total alerts: {len(all_alerts)}",
                parse_mode=ParseMode.HTML
            )
            return

        # Process alerts for state
        available_alerts = process_alerts_for_state(alerts, state)

        if available_alerts.empty:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Found {len(alerts)} alerts, but none available on legal books in {state.upper()}.",
                parse_mode=ParseMode.HTML
            )
            return

        # Send summary
        total_alerts = len(available_alerts)
        tier_label = tier if tier != "ALL" else "All Tiers"
        summary = f"📊 <b>Scan Complete ({state.upper()} - {tier_label})</b>\n"
        summary += f"Found {total_alerts} alerts"
        if api_remaining:
            summary += f"\n🔑 API Quota: {api_remaining} remaining"
        await context.bot.send_message(chat_id=chat_id, text=summary, parse_mode=ParseMode.HTML)

        # Send first batch
        BATCH_SIZE = 5
        for i, (_, row) in enumerate(available_alerts.iterrows()):
            if i >= BATCH_SIZE:
                break
            msg = format_alert_message(row)
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML, link_preview_options=NO_PREVIEW)
            await asyncio.sleep(0.3)

        # Show More button if needed
        remaining = total_alerts - min(BATCH_SIZE, total_alerts)
        if remaining > 0:
            pending_alerts[chat_id] = {
                'alerts': available_alerts,
                'offset': BATCH_SIZE,
                'state': state
            }
            keyboard = [[InlineKeyboardButton(f"📋 Show More ({remaining} remaining)", callback_data="show_more")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"📊 Showing {BATCH_SIZE}/{total_alerts} alerts",
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )

    except Exception as e:
        logger.error(f"Error in state scan: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Scan error: {str(e)}")


async def state_custom_ev_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle state custom EV selection - Step 2: Show Kelly options."""
    query = update.callback_query
    await query.answer()

    # Parse state and EV from callback data: statecustomev_nj_10
    parts = query.data.split("_")
    state = parts[1]
    min_ev = int(parts[2])

    keyboard = [
        [
            InlineKeyboardButton("Kelly>0", callback_data=f"statecustomkelly_{state}_{min_ev}_0.001"),
            InlineKeyboardButton("Kelly≥0.05", callback_data=f"statecustomkelly_{state}_{min_ev}_0.05"),
            InlineKeyboardButton("Kelly≥0.15", callback_data=f"statecustomkelly_{state}_{min_ev}_0.15"),
            InlineKeyboardButton("Kelly≥0.3", callback_data=f"statecustomkelly_{state}_{min_ev}_0.3"),
        ],
        [
            InlineKeyboardButton("Kelly≥0.5", callback_data=f"statecustomkelly_{state}_{min_ev}_0.5"),
            InlineKeyboardButton("Kelly≥0.75", callback_data=f"statecustomkelly_{state}_{min_ev}_0.75"),
            InlineKeyboardButton("Kelly≥1.0", callback_data=f"statecustomkelly_{state}_{min_ev}_1.0"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"📍 <b>Scan for {state.upper()}</b>\n\n"
        f"🔒 <b>Custom Filter - Step 2</b>\n\n"
        f"✅ EV ≥ {min_ev}%\n\n"
        f"Select minimum Kelly (Recc. Units):",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def state_custom_kelly_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle state custom Kelly selection - runs the scan."""
    query = update.callback_query
    await query.answer()

    # Parse from callback data: statecustomkelly_nj_10_0.5
    parts = query.data.split("_")
    state = parts[1]
    min_ev = int(parts[2])
    min_kelly = float(parts[3])

    chat_id = update.effective_chat.id
    legal_books = get_legal_books(state)

    await query.edit_message_text(
        f"🔄 Scanning for <b>{state.upper()}</b>...\n"
        f"📚 Books: {', '.join(legal_books)}\n"
        f"📋 Filter: EV≥{min_ev}%, Kelly≥{min_kelly}",
        parse_mode=ParseMode.HTML
    )

    try:
        df, api_remaining = scan_for_opportunities(state=state, verbose=False)

        if api_remaining:
            database.set_setting('api_remaining', api_remaining)

        if df.empty:
            await context.bot.send_message(chat_id=chat_id, text="No opportunities found. Markets may be closed.")
            return

        all_alerts = get_alerts(df)

        if all_alerts.empty:
            await context.bot.send_message(chat_id=chat_id, text="No alerts meet the thresholds right now.")
            return

        # Apply custom filter
        alerts = all_alerts[
            (all_alerts['EV %'] >= min_ev) &
            (all_alerts['Std. Recc. U'] >= min_kelly)
        ]

        if alerts.empty:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"No alerts match EV≥{min_ev}%, Kelly≥{min_kelly}. Total alerts: {len(all_alerts)}",
                parse_mode=ParseMode.HTML
            )
            return

        # Process alerts for state
        available_alerts = process_alerts_for_state(alerts, state)

        if available_alerts.empty:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Found {len(alerts)} matching alerts, but none available on legal books in {state.upper()}.",
                parse_mode=ParseMode.HTML
            )
            return

        # Send summary
        total_alerts = len(available_alerts)
        summary = f"📊 <b>Scan Complete ({state.upper()} - Custom)</b>\n"
        summary += f"Filter: EV≥{min_ev}%, Kelly≥{min_kelly}\n"
        summary += f"Found {total_alerts} alerts"
        if api_remaining:
            summary += f"\n🔑 API Quota: {api_remaining} remaining"
        await context.bot.send_message(chat_id=chat_id, text=summary, parse_mode=ParseMode.HTML)

        # Send first batch
        BATCH_SIZE = 5
        for i, (_, row) in enumerate(available_alerts.iterrows()):
            if i >= BATCH_SIZE:
                break
            msg = format_alert_message(row)
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML, link_preview_options=NO_PREVIEW)
            await asyncio.sleep(0.3)

        # Show More button if needed
        remaining = total_alerts - min(BATCH_SIZE, total_alerts)
        if remaining > 0:
            pending_alerts[chat_id] = {
                'alerts': available_alerts,
                'offset': BATCH_SIZE,
                'state': state
            }
            keyboard = [[InlineKeyboardButton(f"📋 Show More ({remaining} remaining)", callback_data="show_more")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"📊 Showing {BATCH_SIZE}/{total_alerts} alerts",
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )

    except Exception as e:
        logger.error(f"Error in state custom scan: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Scan error: {str(e)}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command - show all available commands."""
    help_msg = """
📖 <b>NBA Value Alert Bot - Help</b>

<b>🔍 Scanning Commands:</b>
/scan - Run manual scan (shows all tiers)
/state [XX] - State scan with tier filter
/status - Bot status and stats

<b>📚 Per-Book Scans:</b>
/dk /fd /mg /cz /es /fn /br /bp
/rk /bb /ci /rb /fl

<b>⚙️ Settings:</b>
/settings - View current settings
/setinterval [min] - Set scan frequency (1-60)
/setstate [state] - Set state for bet links
/setmax [tier] [n] - Set max alerts per tier
/books - View legal sportsbooks

<b>▶️ Controls:</b>
/pause - Pause automatic alerts
/resume - Resume (select tier + interval)

<b>📊 Alert Tiers:</b>
🔥 FIRE - High confidence (Kelly ≥0.3, Coverage ≥8)
🎯 VALUE_LONGSHOT - Long odds (+500, Kelly ≥0.15)
⚡ OUTLIER - Market outlier (35%+ vs next)
🔒 CUSTOM - Set your own EV% and Kelly thresholds

<b>💡 Tips:</b>
• Use /resume → Custom for DND mode (high thresholds)
• /state lets you filter by tier for any state
• Per-book scans have unlimited "Show 10 More"
"""
    await update.message.reply_text(help_msg, parse_mode=ParseMode.HTML)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command."""
    stats = database.get_alert_stats()
    last_scan = database.get_setting('last_scan', 'Never')
    api_remaining = database.get_setting('api_remaining', 'Unknown')
    current_state = get_state()
    interval = get_scan_interval() // 60

    paused_status = "⏸️ PAUSED" if is_paused() else "▶️ Active"
    hours_status = "✅ Active hours" if is_active_hours() else "😴 Outside active hours"

    now_et = datetime.now(ET).strftime('%I:%M %p ET')

    # Format active hours window for display
    start_hour = config.ACTIVE_HOURS_START
    end_hour = config.ACTIVE_HOURS_END
    start_str = f"{start_hour}AM" if start_hour < 12 else f"{start_hour-12 if start_hour > 12 else 12}PM"
    if start_hour == 0:
        start_str = "12AM"
    end_str = f"{end_hour}AM" if end_hour < 12 else f"{end_hour-12 if end_hour > 12 else 12}PM"
    if end_hour == 24 or end_hour == 0:
        end_str = "12AM"
    active_window = f"{start_str} - {end_str} ET"

    status_msg = f"""
📊 <b>Bot Status</b>

<b>State:</b> {paused_status}
<b>Hours:</b> {hours_status}
<b>Active Window:</b> {active_window}
<b>Current Time:</b> {now_et}
<b>Last Scan:</b> {last_scan}
<b>Scan Interval:</b> {interval} minutes
<b>Bet Links State:</b> {current_state.upper()}
<b>API Quota:</b> {api_remaining} requests remaining

<b>Alerts Today:</b>
🔥 FIRE: {stats['by_tier'].get('FIRE', 0)}
💎 STRONG: {stats['by_tier'].get('STRONG', 0)}
💰 SOLID: {stats['by_tier'].get('SOLID', 0)}
📈 Total Today: {stats['today']}
📚 All Time: {stats['total']}
"""
    await update.message.reply_text(status_msg, parse_mode=ParseMode.HTML)


async def cachestats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cachestats command - show odds cache statistics."""
    if not CACHING_AVAILABLE:
        await update.message.reply_text("❌ Odds caching is not available.")
        return

    try:
        stats = odds_cache.get_cache_stats()

        msg = f"""
📊 <b>Odds Cache Statistics</b>

<b>Scan Sessions:</b> {stats['total_scans']:,}
<b>Odds Snapshots:</b> {stats['total_odds_snapshots']:,}
<b>Market Snapshots:</b> {stats['total_market_snapshots']:,}

<b>Unique Books:</b> {stats['unique_books']}
<b>Unique Players:</b> {stats['unique_players']:,}
<b>Unique Markets:</b> {stats['unique_markets']}

<b>Data Range:</b>
Oldest: {stats['oldest_scan'][:19] if stats['oldest_scan'] else 'N/A'}
Newest: {stats['newest_scan'][:19] if stats['newest_scan'] else 'N/A'}

<b>Database Size:</b> {stats['db_size_mb']:.2f} MB
"""
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Error getting cache stats: {e}")


async def cachecleanup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cachecleanup command - cleanup old cache data."""
    if not CACHING_AVAILABLE:
        await update.message.reply_text("❌ Odds caching is not available.")
        return

    try:
        # Default to 30 days, but allow argument
        days = 30
        if context.args:
            try:
                days = int(context.args[0])
            except ValueError:
                pass

        result = odds_cache.cleanup_old_data(days_to_keep=days)

        msg = f"""
🧹 <b>Cache Cleanup Complete</b>

Removed data older than {days} days:
• Odds snapshots: {result['odds_deleted']:,}
• Market snapshots: {result['markets_deleted']:,}
• Scan sessions: {result['sessions_deleted']:,}
"""
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Error cleaning cache: {e}")


async def betstats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /betstats command - show betting statistics."""
    if not BET_LOGGING_ENABLED:
        await update.message.reply_text("❌ Bet logging is not available.")
        return

    try:
        # Default to 7 days, but allow argument
        days = 7
        if context.args:
            try:
                days = int(context.args[0])
            except ValueError:
                pass

        stats = bet_logger.get_bet_stats(days_back=days)
        roi_by_tier = bet_logger.get_roi_by_tier(days_back=days)

        msg = f"""
📊 <b>Bet Statistics ({days} days)</b>

<b>Total Bets Sent:</b> {stats['total_bets']}
<b>Avg EV:</b> {stats['avg_ev']}%
<b>Avg Odds:</b> {stats['avg_odds']:+d}

<b>By Tier:</b>
🔥 FIRE: {stats['by_tier'].get('FIRE', 0)}
🎯 LONGSHOT: {stats['by_tier'].get('VALUE_LONGSHOT', 0)}
⚡ OUTLIER: {stats['by_tier'].get('OUTLIER', 0)}
"""

        if stats['results']:
            msg += f"""
<b>Results (Graded):</b>
✅ Wins: {stats['results'].get('win', 0)}
❌ Losses: {stats['results'].get('loss', 0)}
➖ Pushes: {stats['results'].get('push', 0)}
<b>P/L:</b> {stats['total_profit_loss']:+.2f} units
"""

        # Show ROI by tier if we have graded results
        if roi_by_tier:
            has_graded = any(t.get('wins', 0) + t.get('losses', 0) > 0 for t in roi_by_tier.values())
            if has_graded:
                msg += "\n<b>ROI by Tier:</b>\n"
                for tier, data in roi_by_tier.items():
                    if data['wins'] + data['losses'] > 0:
                        emoji = {'FIRE': '🔥', 'VALUE_LONGSHOT': '🎯', 'OUTLIER': '⚡'}.get(tier, '📊')
                        msg += f"{emoji} {tier}: {data['win_rate']}% win rate, {data['total_pl']:+.2f}u\n"

        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Error getting bet stats: {e}")


async def grade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /grade command - manually grade bets for a specific date or yesterday."""
    if not BET_GRADING_ENABLED:
        await update.message.reply_text("❌ Bet grading is not available.")
        return

    try:
        # Default to yesterday, but allow date argument
        from datetime import timedelta
        if context.args:
            date = context.args[0]
            # Validate date format
            try:
                datetime.strptime(date, '%Y-%m-%d')
            except ValueError:
                await update.message.reply_text("❌ Invalid date format. Use YYYY-MM-DD")
                return
        else:
            date = (datetime.now(ET) - timedelta(days=1)).strftime('%Y-%m-%d')

        await update.message.reply_text(f"📝 Grading bets for {date}...")

        # Run grading
        results = bet_grader.grade_bets_for_date(date)

        if results['total'] == 0:
            await update.message.reply_text(f"📭 No bets found for {date}")
            return

        # Format results message
        msg = f"""
📊 <b>Grading Results for {date}</b>

<b>Total Bets:</b> {results['total']}
<b>Graded:</b> {results['graded']}
<b>Skipped:</b> {results['skipped']}

<b>Results:</b>
✅ Wins: {results['wins']}
❌ Losses: {results['losses']}
➖ Pushes: {results['pushes']}
🚫 DNP: {results['dnp']}
⚪ Void: {results['void']}

<b>P/L:</b> {results['total_pl']:+.2f} units
"""
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Error in grade command: {e}")
        await update.message.reply_text(f"❌ Error grading bets: {e}")


async def gradeall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /gradeall command - grade all ungraded bets."""
    if not BET_GRADING_ENABLED:
        await update.message.reply_text("❌ Bet grading is not available.")
        return

    try:
        await update.message.reply_text("📝 Grading all ungraded bets...")

        # Run grading for all ungraded bets
        all_results = bet_grader.grade_all_ungraded()

        if not all_results:
            await update.message.reply_text("📭 No ungraded bets found")
            return

        # Aggregate results
        total_bets = sum(r['total'] for r in all_results)
        total_graded = sum(r['graded'] for r in all_results)
        total_wins = sum(r['wins'] for r in all_results)
        total_losses = sum(r['losses'] for r in all_results)
        total_pushes = sum(r['pushes'] for r in all_results)
        total_dnp = sum(r['dnp'] for r in all_results)
        total_pl = sum(r['total_pl'] for r in all_results)

        msg = f"""
📊 <b>Grading Results (All Ungraded)</b>

<b>Dates Processed:</b> {len(all_results)}
<b>Total Bets:</b> {total_bets}
<b>Graded:</b> {total_graded}

<b>Results:</b>
✅ Wins: {total_wins}
❌ Losses: {total_losses}
➖ Pushes: {total_pushes}
🚫 DNP: {total_dnp}

<b>Total P/L:</b> {total_pl:+.2f} units
"""
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Error in gradeall command: {e}")
        await update.message.reply_text(f"❌ Error grading bets: {e}")


async def exportbets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /exportbets command - export all bets to CSV and send to user."""
    if not BET_LOGGING_ENABLED:
        await update.message.reply_text("❌ Bet logging is not enabled.")
        return

    try:
        import os
        from datetime import date

        await update.message.reply_text("📊 Exporting bet history...")

        # Export all bets to CSV
        today = date.today().strftime('%Y-%m-%d')
        csv_path = f"/tmp/bet_history_all_{today}.csv"
        num_bets = bet_logger.export_bets_to_csv(csv_path)

        if num_bets == 0:
            await update.message.reply_text("📭 No bets in database to export")
            return

        if os.path.exists(csv_path):
            # Get summary stats
            stats = bet_logger.get_bet_stats(days_back=365)
            roi_by_tier = bet_logger.get_roi_by_tier(days_back=365)

            # Build summary message
            summary = f"📊 <b>Bet History Export</b>\n\n"
            summary += f"<b>Total Bets:</b> {num_bets}\n"
            summary += f"<b>Avg EV:</b> {stats['avg_ev']}%\n"
            summary += f"<b>Avg Odds:</b> +{stats['avg_odds']}\n\n"

            if roi_by_tier:
                summary += "<b>By Tier:</b>\n"
                for tier, data in roi_by_tier.items():
                    settled = data['settled']
                    if settled > 0:
                        summary += f"• {tier}: {data['wins']}W-{data['losses']}L ({data['win_rate']}%), {data['total_pl']:+.2f}u\n"
                    else:
                        summary += f"• {tier}: {data['total_bets']} bets ({data['pending']} pending)\n"

            with open(csv_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"bet_history_{today}.csv",
                    caption=summary,
                    parse_mode=ParseMode.HTML
                )

            os.remove(csv_path)
            logger.info(f"Exported {num_bets} bets to CSV")
        else:
            await update.message.reply_text("❌ Error creating export file")

    except Exception as e:
        logger.error(f"Error in exportbets command: {e}")
        await update.message.reply_text(f"❌ Error exporting bets: {e}")


async def run_daily_grading(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job to grade yesterday's bets at 7AM ET."""
    if not BET_GRADING_ENABLED:
        logger.warning("Bet grading not available, skipping scheduled grading")
        return

    logger.info("Running scheduled daily grading...")

    try:
        from datetime import timedelta
        yesterday = (datetime.now(ET) - timedelta(days=1)).strftime('%Y-%m-%d')

        results = bet_grader.grade_bets_for_date(yesterday)

        if results['total'] == 0:
            logger.info(f"No bets to grade for {yesterday}")
            return

        # Send summary to chat
        msg = f"""
🌅 <b>Daily Grading Complete</b>

<b>Date:</b> {yesterday}
<b>Bets Graded:</b> {results['graded']}/{results['total']}

<b>Results:</b>
✅ {results['wins']}W / ❌ {results['losses']}L / ➖ {results['pushes']}P
🚫 DNP: {results['dnp']}

<b>P/L:</b> {results['total_pl']:+.2f} units
"""
        await context.bot.send_message(
            chat_id=config.TELEGRAM_CHAT_ID,
            text=msg,
            parse_mode=ParseMode.HTML
        )

        # Export and send CSV with all bets (including yesterday's newly graded)
        try:
            import os
            csv_path = f"/tmp/bet_history_{yesterday}.csv"
            bet_logger.export_bets_to_csv(csv_path)

            if os.path.exists(csv_path):
                with open(csv_path, 'rb') as f:
                    await context.bot.send_document(
                        chat_id=config.TELEGRAM_CHAT_ID,
                        document=f,
                        filename=f"bet_history_{yesterday}.csv",
                        caption="📊 Complete bet history with graded results"
                    )
                os.remove(csv_path)
                logger.info("Sent daily CSV export")
        except Exception as csv_error:
            logger.error(f"Error sending CSV: {csv_error}")

        logger.info(f"Daily grading complete: {results['wins']}W-{results['losses']}L, {results['total_pl']:+.2f}u")

    except Exception as e:
        logger.error(f"Error in scheduled grading: {e}")
        await context.bot.send_message(
            chat_id=config.TELEGRAM_CHAT_ID,
            text=f"❌ Error in daily grading: {e}"
        )


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /settings command."""
    from nba_value_scanner import ALERT_THRESHOLDS

    interval = get_scan_interval() // 60
    current_state = get_state()

    # Get max alerts per tier
    fire_max = get_max_alerts('FIRE')
    strong_max = get_max_alerts('STRONG')
    solid_max = get_max_alerts('SOLID')

    fire_max_str = "unlimited" if fire_max == 0 else str(fire_max)
    strong_max_str = "unlimited" if strong_max == 0 else str(strong_max)
    solid_max_str = "unlimited" if solid_max == 0 else str(solid_max)

    settings_msg = f"""
⚙️ <b>Current Settings</b>

<b>Scan Interval:</b> {interval} minutes
<b>Active Hours:</b> {config.ACTIVE_HOURS_START}:00 - {config.ACTIVE_HOURS_END}:00 ET
<b>State:</b> {current_state.upper()}

<b>Auto-Alert Tiers:</b> {', '.join(config.AUTO_ALERT_TIERS)}

<b>Max Alerts Per Tier:</b>
🔥 FIRE: {fire_max_str}
💎 STRONG: {strong_max_str}
💰 SOLID: {solid_max_str}

<b>Re-Alert Thresholds:</b>
• EV Improvement: +{config.EV_IMPROVEMENT_THRESHOLD}%
• Odds Improvement: +{config.ODDS_IMPROVEMENT_THRESHOLD} points
• Min Time Between: {config.MIN_REALERT_MINUTES} minutes

<b>Alert Thresholds:</b>
"""
    for tier, thresholds in ALERT_THRESHOLDS.items():
        emoji = {'FIRE': '🔥', 'STRONG': '💎', 'SOLID': '💰'}[tier]
        settings_msg += f"{emoji} {tier}: Kelly ≥{thresholds['min_kelly']}, EV ≥{thresholds['min_ev']}%, Coverage ≥{thresholds['min_coverage']}\n"

    settings_msg += """
<b>Commands to Modify:</b>
/setinterval [minutes] - Change scan frequency
/setstate [state] - Change state for bet links
/setmax [tier] [count] - Change max alerts (0=unlimited)
"""

    await update.message.reply_text(settings_msg, parse_mode=ParseMode.HTML)


async def setinterval_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /setinterval command - change scan frequency."""
    if not context.args:
        current = get_scan_interval() // 60
        await update.message.reply_text(
            f"Current interval: {current} minutes\n\n"
            f"Usage: /setinterval [minutes]\n"
            f"Example: /setinterval 5",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        minutes = int(context.args[0])
        if minutes < 1:
            await update.message.reply_text("❌ Interval must be at least 1 minute.")
            return
        if minutes > 60:
            await update.message.reply_text("❌ Interval cannot exceed 60 minutes.")
            return

        seconds = minutes * 60
        database.set_setting('scan_interval', str(seconds))

        # Reschedule the job
        if app_reference and app_reference.job_queue:
            # Remove existing scan jobs
            current_jobs = app_reference.job_queue.get_jobs_by_name('scheduled_scan')
            for job in current_jobs:
                job.schedule_removal()

            # Add new job with updated interval
            app_reference.job_queue.run_repeating(
                run_scheduled_scan,
                interval=seconds,
                first=10,
                name='scheduled_scan'
            )
            logger.info(f"Rescheduled scans to every {minutes} minutes")

        await update.message.reply_text(
            f"✅ Scan interval updated to <b>{minutes} minutes</b>",
            parse_mode=ParseMode.HTML
        )
        logger.info(f"Scan interval changed to {minutes} minutes by user")

    except ValueError:
        await update.message.reply_text("❌ Please provide a valid number of minutes.")


async def setstate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /setstate command - change state for bet links."""
    if not context.args:
        current = get_state()
        legal_books = get_legal_books(current)
        book_names = [config.BOOK_FULL_NAMES.get(b, b) for b in legal_books]
        states_list = ', '.join(config.VALID_STATES).upper()
        await update.message.reply_text(
            f"Current state: <b>{current.upper()}</b>\n"
            f"Legal books: {', '.join(book_names)}\n\n"
            f"Usage: /setstate [state]\n"
            f"Example: /setstate nj\n\n"
            f"Valid states: {states_list}",
            parse_mode=ParseMode.HTML
        )
        return

    state = context.args[0].lower()

    if state not in config.VALID_STATES:
        states_list = ', '.join(config.VALID_STATES).upper()
        await update.message.reply_text(
            f"❌ Invalid state: {state.upper()}\n\n"
            f"Valid states: {states_list}",
            parse_mode=ParseMode.HTML
        )
        return

    # Get legal books for the new state
    legal_books = get_legal_books(state)
    book_names = [config.BOOK_FULL_NAMES.get(b, b) for b in legal_books]

    database.set_setting('state', state)
    await update.message.reply_text(
        f"✅ State updated to <b>{state.upper()}</b>\n\n"
        f"<b>Legal sportsbooks ({len(legal_books)}):</b>\n"
        f"{', '.join(book_names)}\n\n"
        f"Only bets available on these books will be sent.",
        parse_mode=ParseMode.HTML
    )
    logger.info(f"State changed to {state.upper()} by user")


async def books_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /books command - show legal sportsbooks for current or specified state."""
    if context.args:
        state = context.args[0].lower()
        if state not in config.VALID_STATES:
            states_list = ', '.join(config.VALID_STATES).upper()
            await update.message.reply_text(
                f"❌ Invalid state: {state.upper()}\n\n"
                f"Valid states: {states_list}",
                parse_mode=ParseMode.HTML
            )
            return
    else:
        state = get_state()

    legal_books = get_legal_books(state)

    msg = f"📚 <b>Legal Sportsbooks in {state.upper()}</b>\n\n"

    if not legal_books:
        msg += "No legal sportsbooks found for this state."
    else:
        for abbrev in legal_books:
            full_name = config.BOOK_FULL_NAMES.get(abbrev, abbrev)
            msg += f"• {full_name} ({abbrev})\n"

        msg += f"\n<b>Total:</b> {len(legal_books)} sportsbooks"
        msg += f"\n\nℹ️ Only bets available on these books will be sent."

    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


async def setmax_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /setmax command - change max alerts per tier."""
    if len(context.args) < 2:
        fire_max = get_max_alerts('FIRE')
        strong_max = get_max_alerts('STRONG')
        solid_max = get_max_alerts('SOLID')

        await update.message.reply_text(
            f"<b>Current Max Alerts Per Tier:</b>\n"
            f"🔥 FIRE: {fire_max if fire_max > 0 else 'unlimited'}\n"
            f"💎 STRONG: {strong_max if strong_max > 0 else 'unlimited'}\n"
            f"💰 SOLID: {solid_max if solid_max > 0 else 'unlimited'}\n\n"
            f"Usage: /setmax [tier] [count]\n"
            f"Example: /setmax STRONG 3\n"
            f"Use 0 for unlimited.",
            parse_mode=ParseMode.HTML
        )
        return

    tier = context.args[0].upper()
    if tier not in ['FIRE', 'STRONG', 'SOLID']:
        await update.message.reply_text(
            "❌ Invalid tier. Use FIRE, STRONG, or SOLID.",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        count = int(context.args[1])
        if count < 0:
            await update.message.reply_text("❌ Count cannot be negative.")
            return

        database.set_setting(f'max_alerts_{tier.lower()}', str(count))

        emoji = {'FIRE': '🔥', 'STRONG': '💎', 'SOLID': '💰'}[tier]
        count_str = "unlimited" if count == 0 else str(count)

        await update.message.reply_text(
            f"✅ {emoji} {tier} max alerts set to <b>{count_str}</b>",
            parse_mode=ParseMode.HTML
        )
        logger.info(f"Max alerts for {tier} set to {count} by user")

    except ValueError:
        await update.message.reply_text("❌ Please provide a valid number.")


async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /pause command."""
    database.set_setting('paused', 'true')
    await update.message.reply_text("⏸️ Automatic alerts paused. Use /resume to restart.")
    logger.info("Automatic alerts paused by user")


def get_active_tiers() -> list:
    """Get list of active alert tiers from database or config default."""
    tiers = database.get_setting('active_tiers')
    if tiers:
        return tiers.split(',')
    return config.AUTO_ALERT_TIERS


def get_custom_filter() -> dict:
    """Get custom filter settings from database."""
    min_ev = database.get_setting('custom_min_ev')
    min_kelly = database.get_setting('custom_min_kelly')
    min_odds = database.get_setting('custom_min_odds')
    return {
        'min_ev': float(min_ev) if min_ev else 10.0,
        'min_kelly': float(min_kelly) if min_kelly else 0.5,
        'min_odds': int(min_odds) if min_odds else 100
    }


async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /resume command - Step 1: Show tier selection buttons."""
    # Create tier selection buttons (two rows)
    keyboard = [
        [
            InlineKeyboardButton("🔥 Fire", callback_data="tier_FIRE"),
            InlineKeyboardButton("🎯 Longshot", callback_data="tier_VALUE_LONGSHOT"),
            InlineKeyboardButton("⚡ Outlier", callback_data="tier_OUTLIER"),
        ],
        [
            InlineKeyboardButton("📊 All", callback_data="tier_ALL"),
            InlineKeyboardButton("🔒 Custom", callback_data="tier_CUSTOM"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    current_tiers = get_active_tiers()
    if 'CUSTOM' in current_tiers:
        custom = get_custom_filter()
        current_label = f"Custom (EV≥{custom['min_ev']}%, Kelly≥{custom['min_kelly']}, Odds≥+{custom['min_odds']})"
    elif set(current_tiers) == {'FIRE', 'VALUE_LONGSHOT', 'OUTLIER'}:
        current_label = "All"
    else:
        tier_emojis = {'FIRE': '🔥', 'VALUE_LONGSHOT': '🎯', 'OUTLIER': '⚡'}
        current_label = ', '.join(tier_emojis.get(t, t) for t in current_tiers)

    await update.message.reply_text(
        f"📋 Select alert tier (current: {current_label}):",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def tier_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle tier selection button callback - Step 2: Show interval or custom settings buttons."""
    query = update.callback_query
    await query.answer()

    # Parse tier from callback data
    tier_selection = query.data.split("_", 1)[1]  # "FIRE", "VALUE_LONGSHOT", "OUTLIER", "ALL", or "CUSTOM"

    # If CUSTOM selected, show EV threshold options first
    if tier_selection == "CUSTOM":
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

    # Store selected tier(s) in database
    if tier_selection == "ALL":
        tiers = "FIRE,VALUE_LONGSHOT,OUTLIER"
        tier_label = "All tiers"
    else:
        tiers = tier_selection
        tier_emojis = {'FIRE': '🔥 Fire', 'VALUE_LONGSHOT': '🎯 Longshot', 'OUTLIER': '⚡ Outlier'}
        tier_label = tier_emojis.get(tier_selection, tier_selection)

    database.set_setting('active_tiers', tiers)

    # Now show interval selection buttons
    keyboard = [[
        InlineKeyboardButton("30s", callback_data="interval_30"),
        InlineKeyboardButton("45s", callback_data="interval_45"),
        InlineKeyboardButton("1m", callback_data="interval_60"),
        InlineKeyboardButton("3m", callback_data="interval_180"),
        InlineKeyboardButton("5m", callback_data="interval_300"),
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    current_interval = get_scan_interval()
    current_int_label = f"{current_interval}s" if current_interval < 60 else f"{current_interval // 60}m"

    await query.edit_message_text(
        f"✅ {tier_label} selected\n\n⏰ Select scan interval (current: {current_int_label}):",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )
    logger.info(f"Alert tiers set to: {tiers}")


async def custom_ev_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom EV selection - Step 2: Show Kelly threshold options."""
    query = update.callback_query
    await query.answer()

    # Parse EV from callback data
    min_ev = int(query.data.split("_")[1])
    database.set_setting('custom_min_ev', str(min_ev))

    # Now show Kelly threshold options
    keyboard = [
        [
            InlineKeyboardButton("Kelly>0", callback_data="customkelly_0.001"),
            InlineKeyboardButton("Kelly≥0.05", callback_data="customkelly_0.05"),
            InlineKeyboardButton("Kelly≥0.15", callback_data="customkelly_0.15"),
            InlineKeyboardButton("Kelly≥0.3", callback_data="customkelly_0.3"),
        ],
        [
            InlineKeyboardButton("Kelly≥0.5", callback_data="customkelly_0.5"),
            InlineKeyboardButton("Kelly≥0.75", callback_data="customkelly_0.75"),
            InlineKeyboardButton("Kelly≥1.0", callback_data="customkelly_1.0"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"🔒 <b>Custom Filter - Step 2</b>\n\n"
        f"✅ EV ≥ {min_ev}%\n\n"
        f"Select minimum Kelly (Recc. Units):",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def custom_kelly_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom Kelly selection - Step 3: Show min odds options."""
    query = update.callback_query
    await query.answer()

    # Parse Kelly from callback data
    min_kelly = float(query.data.split("_")[1])
    database.set_setting('custom_min_kelly', str(min_kelly))

    # Get saved EV for display
    min_ev = database.get_setting('custom_min_ev')

    # Show min odds selection buttons
    keyboard = [
        [
            InlineKeyboardButton("+100", callback_data="customodds_100"),
            InlineKeyboardButton("+200", callback_data="customodds_200"),
            InlineKeyboardButton("+300", callback_data="customodds_300"),
            InlineKeyboardButton("+500", callback_data="customodds_500"),
        ],
        [
            InlineKeyboardButton("+750", callback_data="customodds_750"),
            InlineKeyboardButton("+1000", callback_data="customodds_1000"),
            InlineKeyboardButton("+1500", callback_data="customodds_1500"),
            InlineKeyboardButton("+2000", callback_data="customodds_2000"),
        ],
        [
            InlineKeyboardButton("+2500", callback_data="customodds_2500"),
            InlineKeyboardButton("+3000", callback_data="customodds_3000"),
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
    query = update.callback_query
    await query.answer()

    # Parse odds from callback data
    min_odds = int(query.data.split("_")[1])
    database.set_setting('custom_min_odds', str(min_odds))
    database.set_setting('active_tiers', 'CUSTOM')

    # Get saved filter values for display
    custom = get_custom_filter()

    # Now show interval selection buttons
    keyboard = [[
        InlineKeyboardButton("30s", callback_data="interval_30"),
        InlineKeyboardButton("45s", callback_data="interval_45"),
        InlineKeyboardButton("1m", callback_data="interval_60"),
        InlineKeyboardButton("3m", callback_data="interval_180"),
        InlineKeyboardButton("5m", callback_data="interval_300"),
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    current_interval = get_scan_interval()
    current_int_label = f"{current_interval}s" if current_interval < 60 else f"{current_interval // 60}m"

    await query.edit_message_text(
        f"✅ Custom filter set: EV≥{custom['min_ev']}%, Kelly≥{custom['min_kelly']}, Odds≥+{min_odds}\n\n"
        f"⏰ Select scan interval (current: {current_int_label}):",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )
    logger.info(f"Custom filter set: EV>={custom['min_ev']}%, Kelly>={custom['min_kelly']}, Odds>=+{min_odds}")


async def interval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle interval selection button callback - Step: Show book selection."""
    query = update.callback_query
    await query.answer()

    # Parse interval from callback data
    interval_seconds = int(query.data.split("_")[1])
    interval_label = f"{interval_seconds}s" if interval_seconds < 60 else f"{interval_seconds // 60}m"

    # Save interval
    database.set_setting('scan_interval', str(interval_seconds))

    # Get legal books for current state
    current_state = get_state()
    legal_books = get_legal_books(current_state)
    excluded = getattr(config, 'EXCLUDED_BOOKS', ['PN', 'BV', 'BO'])
    available_books = [b for b in legal_books if b not in excluded]

    # Get currently selected books
    selected_books = get_selected_books()

    # Book name mapping
    book_names = {
        'DK': 'DraftKings', 'FD': 'FanDuel', 'MG': 'BetMGM', 'CZ': 'Caesars',
        'ES': 'ESPN Bet', 'FN': 'Fanatics', 'BR': 'Bet Rivers', 'RK': 'Hard Rock',
        'BB': 'BetRivers', 'CI': 'Circa', 'FL': 'Fliff', 'PN': 'Pinnacle',
        'BV': 'Bovada', 'BO': 'Betfair'
    }

    # Check if this is default "all" state (empty in DB, not "NONE")
    books_str = database.get_setting('selected_books', '')
    is_default_all = not books_str  # Empty string means default all, "NONE" means explicitly none

    # Create book selection buttons (multi-select with checkmarks)
    keyboard = []
    row = []
    for book in available_books:
        is_selected = book in selected_books or is_default_all  # Default all selected if not set
        checkmark = "✅ " if is_selected else ""
        btn_text = f"{checkmark}{book}"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"togglebook_{book}"))
        if len(row) == 3:
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

    # Get tier display
    active_tiers = get_active_tiers()
    if 'CUSTOM' in active_tiers:
        custom = get_custom_filter()
        tier_display = f"Custom (EV≥{custom['min_ev']}%, Kelly≥{custom['min_kelly']}, Odds≥+{custom['min_odds']})"
    elif set(active_tiers) == {'FIRE', 'VALUE_LONGSHOT', 'OUTLIER'}:
        tier_display = "All tiers"
    else:
        tier_emojis = {'FIRE': '🔥', 'VALUE_LONGSHOT': '🎯', 'OUTLIER': '⚡'}
        tier_display = ', '.join(tier_emojis.get(t, t) for t in active_tiers)

    await query.edit_message_text(
        f"✅ Interval: {interval_label}\n"
        f"📋 Tiers: {tier_display}\n\n"
        f"📖 <b>Select sportsbooks to scan</b> ({current_state.upper()}):\n"
        f"<i>Tap to toggle, then press Done</i>",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


def get_selected_books() -> list:
    """Get list of selected books for auto-scan, or empty list for all books."""
    books_str = database.get_setting('selected_books', '')
    if not books_str or books_str == 'NONE':
        return []
    return [b.strip() for b in books_str.split(',') if b.strip()]


async def toggle_book_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle book toggle button callback."""
    query = update.callback_query
    await query.answer()

    book = query.data.split("_")[1]

    # Get current state's legal books
    current_state = get_state()
    legal_books = get_legal_books(current_state)
    excluded = getattr(config, 'EXCLUDED_BOOKS', ['PN', 'BV', 'BO'])
    available_books = [b for b in legal_books if b not in excluded]

    # Get current selection (empty list means "all books" as default)
    selected_books = get_selected_books()

    # Check if this is the default "all" state (empty in DB)
    is_default_all = not selected_books

    if book == "ALL":
        # Toggle all: if currently all selected, deselect all; otherwise select all
        if is_default_all or set(selected_books) == set(available_books):
            # Deselect all - save special marker "NONE" to distinguish from default
            selected_books = []
            database.set_setting('selected_books', 'NONE')
        else:
            # Select all
            selected_books = available_books.copy()
            database.set_setting('selected_books', ','.join(selected_books))
    else:
        # Toggle individual book
        if is_default_all:
            # First click when default all - start fresh with just this book
            selected_books = [book]
        elif book in selected_books:
            selected_books.remove(book)
        else:
            selected_books.append(book)

        # Save (don't save here for ALL, it's handled above)
        database.set_setting('selected_books', ','.join(selected_books) if selected_books else 'NONE')

    # Rebuild buttons
    keyboard = []
    row = []
    for b in available_books:
        is_selected = b in selected_books
        checkmark = "✅ " if is_selected else ""
        btn_text = f"{checkmark}{b}"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"togglebook_{b}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append([
        InlineKeyboardButton("📚 All Books", callback_data="togglebook_ALL"),
        InlineKeyboardButton("✅ Done", callback_data="books_done"),
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Get tier display
    active_tiers = get_active_tiers()
    if 'CUSTOM' in active_tiers:
        custom = get_custom_filter()
        tier_display = f"Custom (EV≥{custom['min_ev']}%, Kelly≥{custom['min_kelly']}, Odds≥+{custom['min_odds']})"
    elif set(active_tiers) == {'FIRE', 'VALUE_LONGSHOT', 'OUTLIER'}:
        tier_display = "All tiers"
    else:
        tier_emojis = {'FIRE': '🔥', 'VALUE_LONGSHOT': '🎯', 'OUTLIER': '⚡'}
        tier_display = ', '.join(tier_emojis.get(t, t) for t in active_tiers)

    interval_seconds = get_scan_interval()
    interval_label = f"{interval_seconds}s" if interval_seconds < 60 else f"{interval_seconds // 60}m"

    selected_display = ', '.join(selected_books) if selected_books else "None selected"

    await query.edit_message_text(
        f"✅ Interval: {interval_label}\n"
        f"📋 Tiers: {tier_display}\n\n"
        f"📖 <b>Select sportsbooks to scan</b> ({current_state.upper()}):\n"
        f"<i>Selected: {selected_display}</i>",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def books_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'Done' button for book selection - Final step: Resume scanning."""
    query = update.callback_query
    await query.answer()

    # Unpause
    database.set_setting('paused', 'false')

    # Get settings for display
    interval_seconds = get_scan_interval()
    interval_label = f"{interval_seconds}s" if interval_seconds < 60 else f"{interval_seconds // 60}m"

    active_tiers = get_active_tiers()
    tier_emojis = {'FIRE': '🔥', 'VALUE_LONGSHOT': '🎯', 'OUTLIER': '⚡'}
    if 'CUSTOM' in active_tiers:
        custom = get_custom_filter()
        tier_display = f"🔒 Custom (EV≥{custom['min_ev']}%, Kelly≥{custom['min_kelly']}, Odds≥+{custom['min_odds']})"
    elif set(active_tiers) == {'FIRE', 'VALUE_LONGSHOT', 'OUTLIER'}:
        tier_display = "All tiers"
    else:
        tier_display = ', '.join(tier_emojis.get(t, t) for t in active_tiers)

    selected_books = get_selected_books()
    current_state = get_state()
    if selected_books:
        books_display = ', '.join(selected_books)
    else:
        # No specific selection means all legal books
        legal_books = get_legal_books(current_state)
        excluded = getattr(config, 'EXCLUDED_BOOKS', ['PN', 'BV', 'BO'])
        all_books = [b for b in legal_books if b not in excluded]
        books_display = f"All ({', '.join(all_books)})"

    # Reschedule the job
    if app_reference and app_reference.job_queue:
        current_jobs = app_reference.job_queue.get_jobs_by_name('scheduled_scan')
        for job in current_jobs:
            job.schedule_removal()

        app_reference.job_queue.run_repeating(
            run_scheduled_scan,
            interval=interval_seconds,
            first=10,
            name='scheduled_scan'
        )
        logger.info(f"Rescheduled scans to every {interval_seconds} seconds")

    await query.edit_message_text(
        f"▶️ Alerts resumed!\n\n"
        f"📋 Tiers: <b>{tier_display}</b>\n"
        f"⏰ Interval: <b>{interval_label}</b>\n"
        f"📖 Books: <b>{books_display}</b>",
        parse_mode=ParseMode.HTML
    )
    logger.info(f"Automatic alerts resumed with {interval_label} interval, tiers: {','.join(active_tiers)}, books: {books_display}")


async def run_scheduled_scan(context: ContextTypes.DEFAULT_TYPE):
    """Run a scheduled scan and send alerts."""
    if is_paused():
        logger.info("Skipping scan - alerts paused")
        return

    if not is_active_hours():
        logger.info("Skipping scan - outside active hours")
        return

    logger.info("Running scheduled scan...")

    try:
        # Clear expired alerts first
        expired = database.clear_expired_alerts()
        if expired > 0:
            logger.info(f"Cleared {expired} expired alerts")

        # Run scan with current state setting
        current_state = get_state()
        df, api_remaining = scan_for_opportunities(state=current_state, verbose=False)

        # Store API quota in database
        if api_remaining:
            database.set_setting('api_remaining', api_remaining)

        if df.empty:
            logger.info("Scan complete - no opportunities found")
            database.set_setting('last_scan', datetime.now().strftime('%I:%M %p'))
            return

        # Get alerts for active tiers only (from user selection or config default)
        all_alerts = get_alerts(df)
        active_tiers = get_active_tiers()

        # Handle CUSTOM filter
        custom = None
        if 'CUSTOM' in active_tiers:
            custom = get_custom_filter()
            auto_alerts = all_alerts[
                (all_alerts['EV %'] >= custom['min_ev']) &
                (all_alerts['Std. Recc. U'] >= custom['min_kelly']) &
                (all_alerts['Best Odds'] >= custom['min_odds'])
            ]
            logger.info(f"Custom filter applied: EV>={custom['min_ev']}%, Kelly>={custom['min_kelly']}, Odds>=+{custom['min_odds']}, {len(auto_alerts)} alerts match")
        else:
            auto_alerts = all_alerts[all_alerts['Alert Tier'].isin(active_tiers)]

        # Process alerts - find available bets, with fallback to next-best legal book
        # Apply book filter if user selected specific books
        selected_books = get_selected_books()
        available_alerts = process_alerts_for_state(auto_alerts, current_state, allowed_books=selected_books if selected_books else None)

        filtered_count = len(auto_alerts) - len(available_alerts)
        if filtered_count > 0:
            logger.info(f"Filtered out {filtered_count} alerts not available in {current_state.upper()}")

        # CRITICAL: Re-apply custom filter AFTER state processing
        # This ensures bets still meet criteria after being re-calculated for the legal book
        if custom and not available_alerts.empty:
            pre_refilter_count = len(available_alerts)
            available_alerts = available_alerts[
                (available_alerts['EV %'] >= custom['min_ev']) &
                (available_alerts['Std. Recc. U'] >= custom['min_kelly']) &
                (available_alerts['Best Odds'] >= custom['min_odds'])
            ]
            refiltered_count = pre_refilter_count - len(available_alerts)
            if refiltered_count > 0:
                logger.info(f"Re-filter removed {refiltered_count} alerts that no longer met custom thresholds after state processing")

        sent_count = 0
        skipped_count = 0
        sent_by_tier = {'FIRE': 0, 'STRONG': 0}

        for _, row in available_alerts.iterrows():
            tier = row['Alert Tier']

            # Check tier limit
            max_for_tier = get_max_alerts(tier)
            if max_for_tier > 0 and sent_by_tier.get(tier, 0) >= max_for_tier:
                skipped_count += 1
                continue

            unique_key = f"{row['Player']}|{row['Market']}|{row['Side']}|{row['Line']}"
            best_book = row.get('Best Books', '').split(',')[0].strip() if row.get('Best Books') else None

            # Check deduplication
            should_send, reason = database.should_send_alert(
                unique_key=unique_key,
                best_odds=int(row['Best Odds']),
                ev_percent=row['EV %'],
                tier=tier,
                best_book=best_book
            )

            if should_send:
                msg = format_alert_message(row)

                try:
                    await context.bot.send_message(
                        chat_id=config.TELEGRAM_CHAT_ID,
                        text=msg,
                        parse_mode=ParseMode.HTML,
                        link_preview_options=NO_PREVIEW
                    )

                    database.record_sent_alert(
                        unique_key=unique_key,
                        best_odds=int(row['Best Odds']),
                        ev_percent=row['EV %'],
                        tier=tier,
                        game_datetime=row.get('Game Datetime'),
                        best_book=best_book
                    )

                    # Log bet for ROI tracking
                    if BET_LOGGING_ENABLED:
                        try:
                            bet_logger.log_bet(
                                player=row['Player'],
                                market=row['Market'],
                                side=row['Side'],
                                line=row['Line'] if row['Line'] else 0,
                                best_odds=int(row['Best Odds']),
                                fair_odds=int(row['Fair Odds']),
                                ev_percent=row['EV %'],
                                std_kelly=row['Std. Recc. U'],
                                conf_kelly=row['Conf. Adj. Recc. U'],
                                best_books=row['Best Books'],
                                alert_tier=tier,
                                game=row['Game'],
                                game_date=row['Game Date'],
                                game_time=row['Game Time'],
                                game_datetime=row.get('Game Datetime'),
                                market_key=row.get('_market_key'),
                                bet_link=row.get('_link'),
                                coverage=row['Coverage'],
                                calc_type=row['Calc Type'],
                                pct_vs_next=row.get('% vs Next'),
                                next_best_book=row.get('_next_best_book'),
                                next_best_odds=row.get('_next_best_odds'),
                                state=current_state,
                                all_book_odds=row.get('_book_odds'),
                                unique_key=unique_key
                            )
                        except Exception as e:
                            logger.error(f"Failed to log bet: {e}")

                    sent_count += 1
                    sent_by_tier[tier] = sent_by_tier.get(tier, 0) + 1
                    logger.info(f"Sent alert: {unique_key} ({reason})")

                    # Rate limiting
                    await asyncio.sleep(1)

                except Exception as e:
                    logger.error(f"Failed to send alert: {e}")
            else:
                skipped_count += 1
                logger.debug(f"Skipped alert: {unique_key} ({reason})")

        # Update last scan time
        database.set_setting('last_scan', datetime.now().strftime('%I:%M %p'))

        logger.info(f"Scan complete: {sent_count} sent, {skipped_count} skipped, {filtered_count} filtered by state")

    except Exception as e:
        logger.error(f"Error in scheduled scan: {e}")


async def send_startup_message(application: Application):
    """Send a startup notification."""
    interval = get_scan_interval() // 60
    current_state = get_state()

    startup_msg = f"""
🚀 <b>NBA Value Alert Bot Started</b>

✅ Telegram connection verified
✅ Database initialized
⏰ Scan interval: {interval} minutes
📍 State: {current_state.upper()}
🕐 Active hours: {config.ACTIVE_HOURS_START}:00 - {config.ACTIVE_HOURS_END}:00 ET

Bot is now monitoring for +EV opportunities!
"""
    try:
        await application.bot.send_message(
            chat_id=config.TELEGRAM_CHAT_ID,
            text=startup_msg,
            parse_mode=ParseMode.HTML
        )
        logger.info("Startup message sent")
    except Exception as e:
        logger.error(f"Failed to send startup message: {e}")


async def post_init(application: Application):
    """Post-initialization callback."""
    global app_reference
    app_reference = application

    # Clear sent alerts on startup to allow re-sending
    database.reset_alerts()
    logger.info("Cleared sent alerts database on startup")

    await send_startup_message(application)


def main():
    """Main entry point."""
    global app_reference

    logger.info("Starting NBA Value Alert Bot...")

    # Initialize database
    database.init_database()
    logger.info("Database initialized")

    # Create application
    application = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app_reference = application

    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("scan", scan_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("cachestats", cachestats_command))
    application.add_handler(CommandHandler("cachecleanup", cachecleanup_command))
    application.add_handler(CommandHandler("betstats", betstats_command))
    application.add_handler(CommandHandler("grade", grade_command))
    application.add_handler(CommandHandler("gradeall", gradeall_command))
    application.add_handler(CommandHandler("exportbets", exportbets_command))

    # Add callback handlers
    application.add_handler(CallbackQueryHandler(show_more_callback, pattern="^show_more"))
    application.add_handler(CallbackQueryHandler(scan_tier_callback, pattern="^scantier_"))
    application.add_handler(CallbackQueryHandler(scan_custom_ev_callback, pattern="^scancustomev_"))
    application.add_handler(CallbackQueryHandler(scan_custom_kelly_callback, pattern="^scancustomkelly_"))
    application.add_handler(CallbackQueryHandler(scan_custom_odds_callback, pattern="^scancustomodds_"))
    application.add_handler(CallbackQueryHandler(tier_callback, pattern="^tier_"))
    application.add_handler(CallbackQueryHandler(custom_ev_callback, pattern="^customev_"))
    application.add_handler(CallbackQueryHandler(custom_kelly_callback, pattern="^customkelly_"))
    application.add_handler(CallbackQueryHandler(custom_odds_callback, pattern="^customodds_"))
    application.add_handler(CallbackQueryHandler(interval_callback, pattern="^interval_"))
    application.add_handler(CallbackQueryHandler(toggle_book_callback, pattern="^togglebook_"))
    application.add_handler(CallbackQueryHandler(books_done_callback, pattern="^books_done"))
    application.add_handler(CallbackQueryHandler(state_tier_callback, pattern="^statetier_"))
    application.add_handler(CallbackQueryHandler(state_custom_ev_callback, pattern="^statecustomev_"))
    application.add_handler(CallbackQueryHandler(state_custom_kelly_callback, pattern="^statecustomkelly_"))
    application.add_handler(CallbackQueryHandler(book_tier_callback, pattern="^booktier_"))
    application.add_handler(CallbackQueryHandler(book_custom_ev_callback, pattern="^bookcustomev_"))
    application.add_handler(CallbackQueryHandler(book_custom_kelly_callback, pattern="^bookcustomkelly_"))
    application.add_handler(CallbackQueryHandler(book_custom_odds_callback, pattern="^bookcustomodds_"))
    application.add_handler(CallbackQueryHandler(book_show_more_callback, pattern="^bookmore_"))
    application.add_handler(CommandHandler("books", books_command))
    application.add_handler(CommandHandler("setinterval", setinterval_command))
    application.add_handler(CommandHandler("setstate", setstate_command))
    application.add_handler(CommandHandler("setmax", setmax_command))
    application.add_handler(CommandHandler("pause", pause_command))
    application.add_handler(CommandHandler("resume", resume_command))
    application.add_handler(CommandHandler("state", state_command))

    # Per-book scan commands
    application.add_handler(CommandHandler("dk", dk_command))
    application.add_handler(CommandHandler("fd", fd_command))
    application.add_handler(CommandHandler("mg", mg_command))
    application.add_handler(CommandHandler("cz", cz_command))
    application.add_handler(CommandHandler("es", es_command))
    application.add_handler(CommandHandler("fn", fn_command))
    application.add_handler(CommandHandler("br", br_command))
    application.add_handler(CommandHandler("bp", bp_command))
    application.add_handler(CommandHandler("rk", rk_command))
    application.add_handler(CommandHandler("bb", bb_command))
    application.add_handler(CommandHandler("ci", ci_command))
    application.add_handler(CommandHandler("rb", rb_command))
    application.add_handler(CommandHandler("fl", fl_command))

    # Schedule automatic scans with current interval setting
    job_queue = application.job_queue
    interval = get_scan_interval()
    job_queue.run_repeating(
        run_scheduled_scan,
        interval=interval,
        first=10,
        name='scheduled_scan'
    )
    logger.info(f"Scheduled scans every {interval} seconds")

    # Schedule daily grading at 7AM ET
    from datetime import time as dt_time
    grading_time = dt_time(hour=7, minute=0, tzinfo=ET)
    job_queue.run_daily(
        run_daily_grading,
        time=grading_time,
        name='daily_grading'
    )
    logger.info("Scheduled daily grading at 7:00 AM ET")

    # Run the bot
    logger.info("Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
