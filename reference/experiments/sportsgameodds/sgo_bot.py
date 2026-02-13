"""
NBA Value Scanner Test Bot
==========================
Test Telegram bot using SportsGameOdds API.
Runs independently from production bot.

Environment Variables Required:
- TEST_TELEGRAM_BOT_TOKEN: Bot token for test channel
- TEST_TELEGRAM_CHAT_ID: Chat ID for test channel
- SPORTSGAMEODDS_API_KEY: SportsGameOdds API key
- SPORTSGAMEODDS_MODE: 'rest' or 'websocket' (default: rest)
"""

import os
import sys
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Set
from dotenv import load_dotenv

# Add experiment directory and project root to path
EXPERIMENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(EXPERIMENT_DIR))
sys.path.insert(0, EXPERIMENT_DIR)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'src'))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

from scanner import (
    scan_for_opportunities,
    get_alerts,
    format_alert_message,
)
from provider import SportsGameOddsProvider

# Load environment from .env.test if exists, otherwise .env
env_test_path = os.path.join(PROJECT_ROOT, '.env.test')
env_path = os.path.join(PROJECT_ROOT, '.env')
if os.path.exists(env_test_path):
    load_dotenv(env_test_path)
elif os.path.exists(env_path):
    load_dotenv(env_path)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Telegram Settings (TEST channel)
TELEGRAM_BOT_TOKEN = os.getenv("TEST_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TEST_TELEGRAM_CHAT_ID")

# SportsGameOdds Settings
SPORTSGAMEODDS_API_KEY = os.getenv("SPORTSGAMEODDS_API_KEY")
SPORTSGAMEODDS_MODE = os.getenv("SPORTSGAMEODDS_MODE", "rest")

# State for bet links
STATE = os.getenv("STATE", "ny")

# Scanning Settings
SCAN_INTERVAL_SECONDS = int(os.getenv("TEST_SCAN_INTERVAL_SECONDS", "180"))  # 3 minutes default

# Active hours (Eastern Time)
ACTIVE_HOURS_START = int(os.getenv("ACTIVE_HOURS_START", "8"))   # 8 AM EST
ACTIVE_HOURS_END = int(os.getenv("ACTIVE_HOURS_END", "24"))      # Midnight EST

# Alert config
EV_IMPROVEMENT_THRESHOLD = float(os.getenv("EV_IMPROVEMENT_THRESHOLD", "3.0"))
MIN_REALERT_MINUTES = int(os.getenv("MIN_REALERT_MINUTES", "30"))

AUTO_ALERT_TIERS = ['FIRE', 'VALUE_LONGSHOT', 'OUTLIER']
MAX_ALERTS_PER_TIER = {
    'FIRE': 0,           # Unlimited
    'VALUE_LONGSHOT': 5,
    'OUTLIER': 5
}

# =============================================================================
# LOGGING
# =============================================================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('test_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =============================================================================
# GLOBAL STATE
# =============================================================================

# Track sent alerts to avoid duplicates
sent_alerts: Dict[str, Dict] = {}  # bet_id -> {ev_pct, timestamp}

# Provider instance (reused)
provider: Optional[SportsGameOddsProvider] = None

# Current state
current_state = STATE

# Scheduler job reference
scan_job = None

# Auto-scan enabled flag
auto_scan_enabled = True


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def is_active_hours() -> bool:
    """Check if current time is within active scanning hours."""
    # Get current time in EST (UTC-5)
    utc_now = datetime.now(timezone.utc)
    est_offset = timedelta(hours=-5)
    est_now = utc_now + est_offset
    current_hour = est_now.hour

    if ACTIVE_HOURS_END > ACTIVE_HOURS_START:
        return ACTIVE_HOURS_START <= current_hour < ACTIVE_HOURS_END
    else:
        # Handles overnight ranges (e.g., 20-4)
        return current_hour >= ACTIVE_HOURS_START or current_hour < ACTIVE_HOURS_END


def generate_alert_key(row) -> str:
    """Generate unique key for an alert."""
    return f"{row['Player']}|{row['Market']}|{row['Line']}|{row['Side']}|{row['Best Books']}"


def should_send_alert(alert_key: str, ev_pct: float, tier: str) -> bool:
    """Determine if alert should be sent based on previous alerts."""
    if alert_key not in sent_alerts:
        return True

    previous = sent_alerts[alert_key]
    time_since = (datetime.now(timezone.utc) - previous['timestamp']).total_seconds() / 60

    # Always re-alert if enough time has passed
    if time_since >= MIN_REALERT_MINUTES:
        # Re-alert if EV improved significantly
        ev_improvement = ev_pct - previous['ev_pct']
        if ev_improvement >= EV_IMPROVEMENT_THRESHOLD:
            return True

    return False


def get_provider() -> SportsGameOddsProvider:
    """Get or create the SportsGameOdds provider instance."""
    global provider
    if provider is None:
        if not SPORTSGAMEODDS_API_KEY:
            raise ValueError("SPORTSGAMEODDS_API_KEY not set")
        provider = SportsGameOddsProvider(
            api_key=SPORTSGAMEODDS_API_KEY,
            mode=SPORTSGAMEODDS_MODE
        )
    return provider


# =============================================================================
# BOT COMMANDS
# =============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    keyboard = [
        [InlineKeyboardButton("🔍 Scan Now", callback_data="scan")],
        [InlineKeyboardButton("📊 Status", callback_data="status")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_msg = (
        "🏀 <b>NBA Value Scanner - TEST BOT</b>\n\n"
        "📡 <b>Provider:</b> SportsGameOdds\n"
        f"🔄 <b>Mode:</b> {SPORTSGAMEODDS_MODE.upper()}\n"
        f"📍 <b>State:</b> {current_state.upper()}\n\n"
        "<i>This is a TEST environment using SportsGameOdds API.</i>\n"
        "<i>Production bot runs separately using TheOddsAPI.</i>"
    )

    await update.message.reply_text(
        welcome_msg,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /scan command - manual scan."""
    chat_id = update.effective_chat.id

    await context.bot.send_message(
        chat_id=chat_id,
        text="🔄 <b>Starting manual scan...</b>\n\n<i>Using SportsGameOdds API</i>",
        parse_mode=ParseMode.HTML
    )

    try:
        p = get_provider()
        df, requests_remaining = scan_for_opportunities(
            state=current_state,
            verbose=True,
            provider=p
        )

        if df.empty:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ No opportunities found.",
                parse_mode=ParseMode.HTML
            )
            return

        alerts = get_alerts(df)

        if alerts.empty:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"✅ Scan complete.\n"
                    f"📊 {len(df)} opportunities found\n"
                    f"⚠️ No alerts triggered\n"
                    f"🔑 Remaining: {requests_remaining or 'N/A'}"
                ),
                parse_mode=ParseMode.HTML
            )
            return

        # Send summary
        summary = (
            f"✅ <b>Scan Complete</b>\n\n"
            f"📊 Total opportunities: {len(df)}\n"
            f"🔔 Alerts triggered: {len(alerts)}\n"
            f"🔑 API remaining: {requests_remaining or 'N/A'}\n\n"
            f"<i>Sending {len(alerts)} alerts...</i>"
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=summary,
            parse_mode=ParseMode.HTML
        )

        # Send individual alerts
        alerts_sent = 0
        for tier in ['FIRE', 'VALUE_LONGSHOT', 'OUTLIER']:
            tier_alerts = alerts[alerts['Alert Tier'] == tier]
            max_for_tier = MAX_ALERTS_PER_TIER.get(tier, 5)
            tier_count = 0

            for _, row in tier_alerts.iterrows():
                if max_for_tier > 0 and tier_count >= max_for_tier:
                    break

                msg = format_alert_message(row)
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=msg,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
                    )
                    alerts_sent += 1
                    tier_count += 1

                    # Track sent alert
                    alert_key = generate_alert_key(row)
                    sent_alerts[alert_key] = {
                        'ev_pct': row['EV %'],
                        'timestamp': datetime.now(timezone.utc)
                    }

                    await asyncio.sleep(0.5)  # Rate limit

                except Exception as e:
                    logger.error(f"Error sending alert: {e}")

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ Sent {alerts_sent} alerts",
            parse_mode=ParseMode.HTML
        )

    except Exception as e:
        logger.error(f"Scan error: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Scan error: {str(e)[:200]}",
            parse_mode=ParseMode.HTML
        )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command."""
    global auto_scan_enabled

    utc_now = datetime.now(timezone.utc)
    est_now = utc_now - timedelta(hours=5)

    active = "✅ Active" if is_active_hours() else "⏸️ Paused (outside hours)"

    status_msg = (
        "📊 <b>TEST BOT STATUS</b>\n\n"
        f"📡 <b>Provider:</b> SportsGameOdds\n"
        f"🔄 <b>Mode:</b> {SPORTSGAMEODDS_MODE.upper()}\n"
        f"📍 <b>State:</b> {current_state.upper()}\n\n"
        f"⏰ <b>Current Time:</b> {est_now.strftime('%I:%M %p')} EST\n"
        f"📅 <b>Active Hours:</b> {ACTIVE_HOURS_START}:00 - {ACTIVE_HOURS_END}:00 EST\n"
        f"🔔 <b>Auto-Scan:</b> {'Enabled' if auto_scan_enabled else 'Disabled'}\n"
        f"📊 <b>Status:</b> {active}\n\n"
        f"⏱️ <b>Scan Interval:</b> {SCAN_INTERVAL_SECONDS}s\n"
        f"📝 <b>Alerts Tracked:</b> {len(sent_alerts)}"
    )

    await update.message.reply_text(status_msg, parse_mode=ParseMode.HTML)


async def setstate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /setstate command."""
    global current_state

    if not context.args:
        await update.message.reply_text(
            f"Current state: {current_state.upper()}\n\n"
            f"Usage: /setstate <state_code>\n"
            f"Example: /setstate nj"
        )
        return

    new_state = context.args[0].lower()
    valid_states = [
        'az', 'co', 'ct', 'dc', 'il', 'in', 'ia', 'ks', 'ky', 'la',
        'ma', 'md', 'mi', 'mo', 'nc', 'nh', 'nj', 'ny', 'oh', 'or',
        'pa', 'tn', 'va', 'vt', 'wv', 'wy'
    ]

    if new_state not in valid_states:
        await update.message.reply_text(
            f"❌ Invalid state: {new_state}\n\n"
            f"Valid states: {', '.join(s.upper() for s in valid_states)}"
        )
        return

    current_state = new_state
    await update.message.reply_text(f"✅ State updated to: {current_state.upper()}")


async def toggle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /toggle command to enable/disable auto-scanning."""
    global auto_scan_enabled
    auto_scan_enabled = not auto_scan_enabled

    status = "enabled" if auto_scan_enabled else "disabled"
    await update.message.reply_text(f"🔄 Auto-scan {status}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_text = (
        "🏀 <b>NBA Value Scanner - TEST BOT</b>\n\n"
        "<b>Commands:</b>\n"
        "/start - Show main menu\n"
        "/scan - Manual scan for opportunities\n"
        "/status - Show bot status\n"
        "/setstate <code> - Change state (e.g., /setstate nj)\n"
        "/toggle - Enable/disable auto-scanning\n"
        "/help - Show this help\n\n"
        "<b>Provider:</b> SportsGameOdds\n"
        f"<b>Mode:</b> {SPORTSGAMEODDS_MODE.upper()}\n\n"
        "<i>This is a test bot. Production uses TheOddsAPI.</i>"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks."""
    query = update.callback_query
    await query.answer()

    if query.data == "scan":
        # Trigger scan
        await query.message.reply_text("🔄 Starting scan...")
        # Create a fake Update with message for scan_command
        update.message = query.message
        await scan_command(update, context)

    elif query.data == "status":
        # Show status inline
        update.message = query.message
        await status_command(update, context)

    elif query.data == "settings":
        settings_msg = (
            "⚙️ <b>Settings</b>\n\n"
            f"📍 State: {current_state.upper()}\n"
            f"⏱️ Scan interval: {SCAN_INTERVAL_SECONDS}s\n"
            f"🔄 Auto-scan: {'Enabled' if auto_scan_enabled else 'Disabled'}\n\n"
            "Use /setstate to change state\n"
            "Use /toggle to enable/disable auto-scan"
        )
        await query.message.reply_text(settings_msg, parse_mode=ParseMode.HTML)


# =============================================================================
# SCHEDULED SCANNING
# =============================================================================

async def scheduled_scan(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled scan job."""
    global auto_scan_enabled

    if not auto_scan_enabled:
        logger.info("Auto-scan disabled, skipping")
        return

    if not is_active_hours():
        logger.info("Outside active hours, skipping scan")
        return

    logger.info("Starting scheduled scan...")

    try:
        p = get_provider()
        df, requests_remaining = scan_for_opportunities(
            state=current_state,
            verbose=True,
            provider=p
        )

        if df.empty:
            logger.info("No opportunities found")
            return

        alerts = get_alerts(df)

        if alerts.empty:
            logger.info(f"Scan complete: {len(df)} opportunities, no alerts")
            return

        # Send alerts
        alerts_sent = 0
        for tier in AUTO_ALERT_TIERS:
            tier_alerts = alerts[alerts['Alert Tier'] == tier]
            max_for_tier = MAX_ALERTS_PER_TIER.get(tier, 5)
            tier_count = 0

            for _, row in tier_alerts.iterrows():
                if max_for_tier > 0 and tier_count >= max_for_tier:
                    break

                alert_key = generate_alert_key(row)

                # Check if should send
                if not should_send_alert(alert_key, row['EV %'], tier):
                    continue

                msg = format_alert_message(row)
                try:
                    await context.bot.send_message(
                        chat_id=TELEGRAM_CHAT_ID,
                        text=msg,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
                    )
                    alerts_sent += 1
                    tier_count += 1

                    # Track alert
                    sent_alerts[alert_key] = {
                        'ev_pct': row['EV %'],
                        'timestamp': datetime.now(timezone.utc)
                    }

                    await asyncio.sleep(0.5)

                except Exception as e:
                    logger.error(f"Error sending alert: {e}")

        logger.info(f"Scheduled scan complete: {alerts_sent} alerts sent")

    except Exception as e:
        logger.error(f"Scheduled scan error: {e}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Start the test bot."""
    # Validate config
    if not TELEGRAM_BOT_TOKEN:
        print("❌ ERROR: TEST_TELEGRAM_BOT_TOKEN not set")
        print("   Set this in .env.test or environment")
        sys.exit(1)

    if not TELEGRAM_CHAT_ID:
        print("❌ ERROR: TEST_TELEGRAM_CHAT_ID not set")
        print("   Set this in .env.test or environment")
        print("\n   To get your chat ID:")
        print(f"   1. Add the bot to your test channel")
        print(f"   2. Send a message in the channel")
        print(f"   3. Visit: https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates")
        print(f"   4. Look for 'chat':{'{'}'id': XXXXXXX{'}'}")
        sys.exit(1)

    if not SPORTSGAMEODDS_API_KEY:
        print("❌ ERROR: SPORTSGAMEODDS_API_KEY not set")
        print("   Set this in .env.test or environment")
        sys.exit(1)

    print("=" * 60)
    print("NBA VALUE SCANNER - TEST BOT")
    print("=" * 60)
    print(f"📡 Provider: SportsGameOdds")
    print(f"🔄 Mode: {SPORTSGAMEODDS_MODE.upper()}")
    print(f"📍 State: {current_state.upper()}")
    print(f"⏱️ Scan Interval: {SCAN_INTERVAL_SECONDS}s")
    print(f"📅 Active Hours: {ACTIVE_HOURS_START}:00 - {ACTIVE_HOURS_END}:00 EST")
    print("=" * 60)

    # Build application
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("setstate", setstate_command))
    app.add_handler(CommandHandler("toggle", toggle_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button_callback))

    # Schedule automatic scanning
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_repeating(
            scheduled_scan,
            interval=SCAN_INTERVAL_SECONDS,
            first=30  # Start first scan 30 seconds after bot starts
        )
        print(f"✅ Scheduled scanning every {SCAN_INTERVAL_SECONDS}s")

    print("\n🚀 Bot starting...")
    print(f"💬 Sending alerts to chat: {TELEGRAM_CHAT_ID}")
    print("\nPress Ctrl+C to stop\n")

    # Start bot
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
