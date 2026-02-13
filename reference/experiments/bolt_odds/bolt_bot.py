#!/usr/bin/env python3
"""
NBA Value Alert Bot - BOLT ODDS TEST VERSION
=============================================

Test bot using Bolt Odds real-time WebSocket streaming.
Sends alerts to the test Telegram channel.

Commands:
- /start - Show status
- /scan - Manual scan
- /setstate <state> - Change state (e.g., /setstate nj)
- /status - Show current status
"""

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import pandas as pd
import pytz
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

# Add project paths for imports
import sys
EXPERIMENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(EXPERIMENT_DIR))
sys.path.insert(0, EXPERIMENT_DIR)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'src'))

# Use Bolt Odds scanner
from scanner import (
    scan_for_opportunities,
    get_alerts,
    format_alert_message,
    ensure_connected,
    _store,
    STATE_LEGAL_BOOKS,
)

# Load environment from .env.test or .env
from dotenv import load_dotenv
env_test_path = os.path.join(PROJECT_ROOT, '.env.test')
env_path = os.path.join(PROJECT_ROOT, '.env')
if os.path.exists(env_test_path):
    load_dotenv(env_test_path)
elif os.path.exists(env_path):
    load_dotenv(env_path)

# =============================================================================
# CONFIGURATION - TEST BOT CREDENTIALS (hardcoded for test environment)
# =============================================================================

# TEST channel credentials - DO NOT use production credentials here
TEST_BOT_TOKEN = "8433115695:AAHIY27eEnfKMaL-SsVQL5dXUKuewpSpm18"
TEST_CHAT_ID = "-1003336875829"  # SGO_Test_Bot channel

TELEGRAM_BOT_TOKEN = os.getenv("TEST_TELEGRAM_BOT_TOKEN") or TEST_BOT_TOKEN
TELEGRAM_CHAT_ID = os.getenv("TEST_TELEGRAM_CHAT_ID") or TEST_CHAT_ID

# Bolt Odds settings
BOLT_SCAN_INTERVAL = int(os.getenv("BOLT_SCAN_INTERVAL", "10"))  # 10 seconds default
ACTIVE_HOURS_START = int(os.getenv("ACTIVE_HOURS_START", "10"))   # 10 AM EST
ACTIVE_HOURS_END = int(os.getenv("ACTIVE_HOURS_END", "24"))       # Midnight EST

# Valid states
VALID_STATES = list(STATE_LEGAL_BOOKS.keys())

# =============================================================================
# GLOBAL STATE
# =============================================================================

current_state = os.getenv("STATE", "ny").lower()
sent_alerts = {}  # bet_id -> (timestamp, ev)
scan_count = 0
total_alerts_sent = 0

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(os.path.join(EXPERIMENT_DIR, "bolt_test_bot.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Timezone
ET = pytz.timezone('US/Eastern')


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def is_active_hours() -> bool:
    """Check if we're in active scanning hours."""
    now = datetime.now(ET)
    hour = now.hour
    return ACTIVE_HOURS_START <= hour < ACTIVE_HOURS_END


def should_send_alert(bet_id: str, ev: float) -> bool:
    """Check if we should send this alert (not a recent duplicate)."""
    if not bet_id:
        return False

    if bet_id in sent_alerts:
        last_time, last_ev = sent_alerts[bet_id]
        minutes_ago = (datetime.now() - last_time).total_seconds() / 60

        # Re-alert if: 30+ minutes passed OR EV improved by 3%+
        if minutes_ago < 30 and ev < last_ev + 3.0:
            return False

    return True


# =============================================================================
# COMMAND HANDLERS
# =============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    global current_state

    live_count = sum(1 for g in _store.games.values() if g.get('is_live', False))
    pregame_count = len(_store.games) - live_count

    msg = (
        "⚡ <b>Bolt Odds Test Bot</b>\n\n"
        f"📍 State: <b>{current_state.upper()}</b>\n"
        f"🔄 Scan interval: {BOLT_SCAN_INTERVAL}s\n"
        f"⏰ Active hours: {ACTIVE_HOURS_START}:00 - {ACTIVE_HOURS_END}:00 EST\n\n"
        f"📊 WebSocket updates: {_store.update_count}\n"
        f"🏀 Games: {pregame_count} pre-game, {live_count} live (filtered)\n\n"
        "<b>Commands:</b>\n"
        "/scan - Manual scan\n"
        "/setstate &lt;state&gt; - Change state\n"
        "/status - Show status"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command."""
    global current_state, scan_count, total_alerts_sent

    now_est = datetime.now(ET)
    active = "✅ Active" if is_active_hours() else "⏸️ Paused"

    live_count = sum(1 for g in _store.games.values() if g.get('is_live', False))
    pregame_count = len(_store.games) - live_count

    legal_books = STATE_LEGAL_BOOKS.get(current_state, [])

    msg = (
        "📊 <b>Bot Status</b>\n\n"
        f"📍 State: <b>{current_state.upper()}</b>\n"
        f"📚 Legal books: {', '.join(legal_books)}\n\n"
        f"⏰ Time: {now_est.strftime('%I:%M %p EST')}\n"
        f"📊 Status: {active}\n\n"
        f"🔄 Scans: {scan_count}\n"
        f"📨 Alerts sent: {total_alerts_sent}\n"
        f"📡 WS updates: {_store.update_count}\n"
        f"🏀 Games: {pregame_count} pre-game, {live_count} live"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


async def setstate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /setstate command."""
    global current_state

    if not context.args:
        msg = (
            f"Current state: <b>{current_state.upper()}</b>\n\n"
            f"Usage: /setstate &lt;state_code&gt;\n"
            f"Example: /setstate nj\n\n"
            f"Valid states: {', '.join(s.upper() for s in VALID_STATES)}"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return

    new_state = context.args[0].lower()

    if new_state not in VALID_STATES:
        await update.message.reply_text(
            f"❌ Invalid state: {new_state}\n\n"
            f"Valid states: {', '.join(s.upper() for s in VALID_STATES)}"
        )
        return

    old_state = current_state
    current_state = new_state

    legal_books = STATE_LEGAL_BOOKS.get(current_state, [])
    await update.message.reply_text(
        f"✅ State changed: {old_state.upper()} → <b>{current_state.upper()}</b>\n\n"
        f"📚 Legal books: {', '.join(legal_books)}",
        parse_mode=ParseMode.HTML
    )
    logger.info(f"State changed to {current_state.upper()}")


async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /scan command - manual scan."""
    global current_state

    await update.message.reply_text("🔄 Scanning...")

    scan_time = datetime.now(timezone.utc)

    try:
        df, status = scan_for_opportunities(state=current_state, verbose=False)

        if df.empty:
            await update.message.reply_text("❌ No opportunities found")
            return

        alerts = get_alerts(df, state=current_state)

        live_count = sum(1 for g in _store.games.values() if g.get('is_live', False))
        pregame_count = len(_store.games) - live_count

        summary = (
            f"✅ <b>Scan Complete</b>\n\n"
            f"🏀 Games: {pregame_count} pre-game, {live_count} live (filtered)\n"
            f"📊 Opportunities: {len(df)}\n"
            f"🔔 Alerts: {len(alerts)}\n"
            f"📍 State: {current_state.upper()}"
        )
        await update.message.reply_text(summary, parse_mode=ParseMode.HTML)

        # Send alerts
        for _, row in alerts.head(10).iterrows():
            msg = format_alert_message(row, scan_time=scan_time)
            await update.message.reply_text(
                msg,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            await asyncio.sleep(0.3)

        if len(alerts) > 10:
            await update.message.reply_text(f"<i>... and {len(alerts) - 10} more alerts</i>", parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Manual scan error: {e}")
        await update.message.reply_text(f"❌ Scan error: {str(e)[:200]}")


# =============================================================================
# SCHEDULED SCANNING
# =============================================================================

async def scheduled_scan(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled scan job."""
    global current_state, scan_count, total_alerts_sent, sent_alerts

    if not is_active_hours():
        return

    scan_count += 1
    scan_time = datetime.now(timezone.utc)

    try:
        df, status = scan_for_opportunities(state=current_state, verbose=False)

        if df.empty:
            return

        alerts = get_alerts(df, state=current_state)

        if alerts.empty:
            return

        # Send new alerts
        for _, row in alerts.iterrows():
            bet_id = row.get('bet_id', '')

            if not should_send_alert(bet_id, row['ev']):
                continue

            msg = format_alert_message(row, scan_time=scan_time)

            try:
                await context.bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=msg,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
                total_alerts_sent += 1
                sent_alerts[bet_id] = (datetime.now(), row['ev'])
                logger.info(f"Alert: {row['player']} {row['market']} {row['best_book']} {row['best_price']:+d}")

                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Send error: {e}")

        # Log status periodically
        if scan_count % 60 == 0:
            logger.info(f"Status: {scan_count} scans, {total_alerts_sent} alerts, {_store.update_count} WS updates")

    except Exception as e:
        logger.error(f"Scheduled scan error: {e}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Start the bot."""
    global current_state

    if not TELEGRAM_BOT_TOKEN:
        print("❌ ERROR: TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)

    if not TELEGRAM_CHAT_ID:
        print("❌ ERROR: TELEGRAM_CHAT_ID not set")
        sys.exit(1)

    print("=" * 60)
    print("BOLT ODDS TEST BOT")
    print("=" * 60)
    print(f"📍 State: {current_state.upper()}")
    print(f"🔄 Scan interval: {BOLT_SCAN_INTERVAL}s")
    print(f"⏰ Active hours: {ACTIVE_HOURS_START}:00 - {ACTIVE_HOURS_END}:00 EST")
    print(f"💬 Chat ID: {TELEGRAM_CHAT_ID}")
    print("=" * 60)

    # Connect to WebSocket
    print("Connecting to Bolt Odds WebSocket...")
    ensure_connected()
    print(f"✅ Connected! Updates: {_store.update_count}")

    # Build application
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Add command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("setstate", setstate_command))
    app.add_handler(CommandHandler("scan", scan_command))

    # Schedule automatic scanning
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(
            scheduled_scan,
            interval=BOLT_SCAN_INTERVAL,
            first=10  # Start 10 seconds after bot starts
        )
        print(f"✅ Scheduled scanning every {BOLT_SCAN_INTERVAL}s")

    print("\n🚀 Bot starting...")
    print("Press Ctrl+C to stop\n")

    # Run bot
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
