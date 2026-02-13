"""
NBA Value Alert Bot - Database Operations
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Tuple
import config


def get_connection():
    """Get a database connection."""
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize the database with required tables."""
    conn = get_connection()
    cursor = conn.cursor()

    # Sent alerts table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sent_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unique_key TEXT NOT NULL,
            best_odds INTEGER,
            ev_percent REAL,
            tier TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            game_datetime TIMESTAMP,
            best_book TEXT,
            UNIQUE(unique_key)
        )
    """)

    # Add best_book column if it doesn't exist (migration for existing DBs)
    try:
        cursor.execute("ALTER TABLE sent_alerts ADD COLUMN best_book TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Bot settings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # Create index for faster lookups
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sent_alerts_unique_key
        ON sent_alerts(unique_key)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sent_alerts_game_datetime
        ON sent_alerts(game_datetime)
    """)

    conn.commit()
    conn.close()


def get_setting(key: str, default: str = None) -> Optional[str]:
    """Get a setting value from the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM bot_settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row['value'] if row else default


def set_setting(key: str, value: str):
    """Set a setting value in the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)
    """, (key, value))
    conn.commit()
    conn.close()


def should_send_alert(
    unique_key: str,
    best_odds: int,
    ev_percent: float,
    tier: str,
    best_book: str = None
) -> Tuple[bool, str]:
    """
    Determine if an alert should be sent based on deduplication rules.

    Duplicate detection is based on Player|Market|Side|Line only.

    STRICT DUPLICATE PREVENTION:
    A bet is NEVER re-sent if:
    - Same unique_key with same book and same odds (absolute catch-all)
    - Same unique_key within 30 minutes
    - Same unique_key with less than 3% EV improvement (after 30 min)

    A bet IS re-sent only if:
    - It's a completely new bet (not seen before)
    - After 30+ minutes AND EV improved by 3%+
    - After 30+ minutes AND odds improved by 20+ on same book

    Returns:
        Tuple of (should_send, reason)
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT best_odds, ev_percent, sent_at, best_book
        FROM sent_alerts
        WHERE unique_key = ?
    """, (unique_key,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return True, "new_alert"

    prev_odds = row['best_odds']
    prev_ev = row['ev_percent']
    prev_book = row['best_book']
    sent_at = datetime.fromisoformat(row['sent_at'])

    # CATCH-ALL #1: If exact same book and same/worse odds, NEVER re-send
    # This is the strictest check and ignores all other conditions
    if best_book and prev_book and best_book == prev_book:
        if best_odds <= prev_odds:
            return False, f"same_book_no_improvement ({best_book} {prev_odds}→{best_odds})"

    # Check minimum time threshold - never re-alert within 30 minutes
    time_since_last = datetime.now() - sent_at
    if time_since_last < timedelta(minutes=config.MIN_REALERT_MINUTES):
        return False, f"sent_recently ({time_since_last.seconds // 60}m ago)"

    # After 30 minutes, check for meaningful improvements

    # Re-alert if EV improved significantly (3%+)
    ev_improvement = ev_percent - prev_ev
    if ev_improvement >= config.EV_IMPROVEMENT_THRESHOLD:
        return True, f"ev_improved (+{ev_improvement:.1f}%)"

    # Re-alert if odds improved significantly (20+ points) on same book
    if best_book and prev_book and best_book == prev_book:
        odds_improvement = best_odds - prev_odds
        if odds_improvement >= 20:
            return True, f"odds_improved ({prev_odds}→{best_odds})"

    # Don't re-send for any other reason (different book, different tier, small changes)
    return False, "already_sent"


def record_sent_alert(
    unique_key: str,
    best_odds: int,
    ev_percent: float,
    tier: str,
    game_datetime: datetime = None,
    best_book: str = None
):
    """Record that an alert was sent."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO sent_alerts
        (unique_key, best_odds, ev_percent, tier, sent_at, game_datetime, best_book)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        unique_key,
        best_odds,
        ev_percent,
        tier,
        datetime.now().isoformat(),
        game_datetime.isoformat() if game_datetime else None,
        best_book
    ))

    conn.commit()
    conn.close()


def clear_expired_alerts():
    """Clear alerts for games that have already started."""
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute("""
        DELETE FROM sent_alerts
        WHERE game_datetime IS NOT NULL AND game_datetime < ?
    """, (now,))

    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    return deleted


def get_alert_stats() -> dict:
    """Get statistics about sent alerts."""
    conn = get_connection()
    cursor = conn.cursor()

    # Total alerts today
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    cursor.execute("""
        SELECT COUNT(*) as count FROM sent_alerts
        WHERE sent_at >= ?
    """, (today.isoformat(),))
    today_count = cursor.fetchone()['count']

    # Alerts by tier today
    cursor.execute("""
        SELECT tier, COUNT(*) as count FROM sent_alerts
        WHERE sent_at >= ?
        GROUP BY tier
    """, (today.isoformat(),))
    tier_counts = {row['tier']: row['count'] for row in cursor.fetchall()}

    # Total all time
    cursor.execute("SELECT COUNT(*) as count FROM sent_alerts")
    total_count = cursor.fetchone()['count']

    conn.close()

    return {
        'today': today_count,
        'by_tier': tier_counts,
        'total': total_count
    }


def reset_alerts():
    """Clear all sent alerts (useful for testing)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sent_alerts")
    conn.commit()
    conn.close()
