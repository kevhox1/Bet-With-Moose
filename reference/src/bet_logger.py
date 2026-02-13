"""
NBA Value Alert Bot - Bet Logger
=================================
Lightweight logging of all bets sent through the bot for ROI tracking.
Stores complete bet information for later grading and analysis.
"""

import sqlite3
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import logging
import json

logger = logging.getLogger(__name__)

BET_LOG_DB_PATH = 'bet_log.db'


def get_connection(db_path: str = None):
    """Get a database connection."""
    path = db_path or BET_LOG_DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_bet_log_database(db_path: str = None):
    """Initialize the bet log database."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Main bet log table - one row per bet sent
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bet_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            -- Timestamps
            sent_at TIMESTAMP NOT NULL,
            game_date TEXT,
            game_time TEXT,
            game_datetime TIMESTAMP,
            -- Game info
            game TEXT,
            home_team TEXT,
            away_team TEXT,
            -- Bet details
            player TEXT NOT NULL,
            market TEXT NOT NULL,
            market_key TEXT,
            side TEXT NOT NULL,
            line REAL,
            -- Odds and value
            best_odds INTEGER NOT NULL,
            fair_odds INTEGER,
            ev_percent REAL,
            std_kelly REAL,
            conf_kelly REAL,
            -- Book info
            best_books TEXT,
            book_used TEXT,
            bet_link TEXT,
            -- Coverage and calculation
            coverage INTEGER,
            calc_type TEXT,
            pct_vs_next REAL,
            next_best_book TEXT,
            next_best_odds INTEGER,
            -- Alert classification
            alert_tier TEXT,
            -- State/filter info
            state TEXT,
            -- All book odds snapshot (JSON)
            all_book_odds JSON,
            -- Result tracking (filled in later by grader)
            result TEXT,
            result_updated_at TIMESTAMP,
            profit_loss REAL,
            -- Unique identifier for this bet opportunity
            unique_key TEXT NOT NULL
        )
    """)

    # Daily summary table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE NOT NULL,
            total_bets INTEGER DEFAULT 0,
            fire_bets INTEGER DEFAULT 0,
            longshot_bets INTEGER DEFAULT 0,
            outlier_bets INTEGER DEFAULT 0,
            avg_ev REAL,
            avg_odds INTEGER,
            -- Results (updated by grader)
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            pushes INTEGER DEFAULT 0,
            pending INTEGER DEFAULT 0,
            total_profit_loss REAL DEFAULT 0,
            roi_percent REAL
        )
    """)

    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bet_log_sent_at ON bet_log(sent_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bet_log_player ON bet_log(player)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bet_log_game_date ON bet_log(game_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bet_log_tier ON bet_log(alert_tier)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bet_log_result ON bet_log(result)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bet_log_unique_key ON bet_log(unique_key)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bet_log_unique_date ON bet_log(unique_key, game_date)")

    conn.commit()
    conn.close()
    logger.info("Bet log database initialized")


def log_bet(
    player: str,
    market: str,
    side: str,
    line: float,
    best_odds: int,
    fair_odds: int,
    ev_percent: float,
    std_kelly: float,
    conf_kelly: float,
    best_books: str,
    alert_tier: str,
    game: str = None,
    game_date: str = None,
    game_time: str = None,
    game_datetime: datetime = None,
    home_team: str = None,
    away_team: str = None,
    market_key: str = None,
    book_used: str = None,
    bet_link: str = None,
    coverage: int = None,
    calc_type: str = None,
    pct_vs_next: float = None,
    next_best_book: str = None,
    next_best_odds: int = None,
    state: str = None,
    all_book_odds: Dict = None,
    unique_key: str = None,
    db_path: str = None
) -> Optional[int]:
    """
    Log a bet that was sent to the user.
    Returns the bet log ID, or None if bet already exists for this game date.

    Prevents duplicate logging when re-alerts are sent for improved odds/EV.
    Only the first occurrence of each unique bet per game date is logged.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    sent_at = datetime.now(timezone.utc).isoformat()

    # Generate unique key if not provided
    if not unique_key:
        unique_key = f"{player}|{market}|{side}|{line}"

    # Check if this bet was already logged for this game date
    # This prevents double-counting when re-alerts are sent
    cursor.execute("""
        SELECT id FROM bet_log
        WHERE unique_key = ? AND game_date = ?
        LIMIT 1
    """, (unique_key, game_date))

    existing = cursor.fetchone()
    if existing:
        conn.close()
        logger.debug(f"Skipping duplicate bet: {player} {market} {side} {line} (already logged as #{existing[0]})")
        return None

    cursor.execute("""
        INSERT INTO bet_log (
            sent_at, game_date, game_time, game_datetime,
            game, home_team, away_team,
            player, market, market_key, side, line,
            best_odds, fair_odds, ev_percent, std_kelly, conf_kelly,
            best_books, book_used, bet_link,
            coverage, calc_type, pct_vs_next, next_best_book, next_best_odds,
            alert_tier, state, all_book_odds, unique_key
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        sent_at, game_date, game_time,
        game_datetime.isoformat() if game_datetime else None,
        game, home_team, away_team,
        player, market, market_key, side, line,
        best_odds, fair_odds, ev_percent, std_kelly, conf_kelly,
        best_books, book_used, bet_link,
        coverage, calc_type, pct_vs_next, next_best_book, next_best_odds,
        alert_tier, state,
        json.dumps(all_book_odds) if all_book_odds else None,
        unique_key
    ))

    bet_id = cursor.lastrowid
    conn.commit()
    conn.close()

    logger.debug(f"Logged bet #{bet_id}: {player} {market} {side} {line}")
    return bet_id


def update_bet_result(
    bet_id: int,
    result: str,
    profit_loss: float = None,
    db_path: str = None
):
    """
    Update a bet with its result.
    result: 'win', 'loss', 'push', 'void'
    profit_loss: Profit/loss in units (e.g., +1.5 for a win at +150 odds)
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE bet_log
        SET result = ?, profit_loss = ?, result_updated_at = ?
        WHERE id = ?
    """, (result, profit_loss, datetime.now(timezone.utc).isoformat(), bet_id))

    conn.commit()
    conn.close()


def get_bet_stats(days_back: int = 7, db_path: str = None) -> Dict:
    """Get betting statistics for the past N days."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()

    # Total bets
    cursor.execute("SELECT COUNT(*) FROM bet_log WHERE sent_at >= ?", (cutoff,))
    total_bets = cursor.fetchone()[0]

    # By tier
    cursor.execute("""
        SELECT alert_tier, COUNT(*) as count
        FROM bet_log
        WHERE sent_at >= ?
        GROUP BY alert_tier
    """, (cutoff,))
    by_tier = {row['alert_tier']: row['count'] for row in cursor.fetchall()}

    # Average EV
    cursor.execute("SELECT AVG(ev_percent) FROM bet_log WHERE sent_at >= ?", (cutoff,))
    avg_ev = cursor.fetchone()[0] or 0

    # Average odds
    cursor.execute("SELECT AVG(best_odds) FROM bet_log WHERE sent_at >= ?", (cutoff,))
    avg_odds = cursor.fetchone()[0] or 0

    # Results (if graded)
    cursor.execute("""
        SELECT result, COUNT(*) as count
        FROM bet_log
        WHERE sent_at >= ? AND result IS NOT NULL
        GROUP BY result
    """, (cutoff,))
    results = {row['result']: row['count'] for row in cursor.fetchall()}

    # Total P/L
    cursor.execute("""
        SELECT SUM(profit_loss) FROM bet_log
        WHERE sent_at >= ? AND profit_loss IS NOT NULL
    """, (cutoff,))
    total_pl = cursor.fetchone()[0] or 0

    conn.close()

    return {
        'total_bets': total_bets,
        'by_tier': by_tier,
        'avg_ev': round(avg_ev, 2),
        'avg_odds': int(avg_odds),
        'results': results,
        'total_profit_loss': round(total_pl, 2),
        'days': days_back
    }


def get_recent_bets(limit: int = 20, db_path: str = None) -> List[Dict]:
    """Get the most recent bets."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM bet_log
        ORDER BY sent_at DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_ungraded_bets(db_path: str = None) -> List[Dict]:
    """Get bets that haven't been graded yet (for games that have finished)."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Get bets where result is NULL and game_datetime is in the past
    now = datetime.now(timezone.utc).isoformat()

    cursor.execute("""
        SELECT * FROM bet_log
        WHERE result IS NULL
        AND game_datetime IS NOT NULL
        AND game_datetime < ?
        ORDER BY game_datetime ASC
    """, (now,))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_bets_by_date(date: str, db_path: str = None) -> List[Dict]:
    """Get all bets for a specific game date (YYYY-MM-DD)."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM bet_log
        WHERE game_date = ?
        ORDER BY sent_at ASC
    """, (date,))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_bets_by_player(player: str, db_path: str = None) -> List[Dict]:
    """Get all bets for a specific player."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM bet_log
        WHERE player LIKE ?
        ORDER BY sent_at DESC
    """, (f"%{player}%",))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def export_bets_to_csv(output_path: str, start_date: str = None, end_date: str = None, db_path: str = None):
    """Export bets to CSV file."""
    import csv

    conn = get_connection(db_path)
    cursor = conn.cursor()

    query = "SELECT * FROM bet_log WHERE 1=1"
    params = []

    if start_date:
        query += " AND game_date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND game_date <= ?"
        params.append(end_date)

    query += " ORDER BY sent_at ASC"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    if rows:
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([desc[0] for desc in cursor.description])
            writer.writerows(rows)
        logger.info(f"Exported {len(rows)} bets to {output_path}")

    conn.close()
    return len(rows)


def get_roi_by_tier(days_back: int = 30, db_path: str = None) -> Dict:
    """Calculate ROI by alert tier."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()

    cursor.execute("""
        SELECT
            alert_tier,
            COUNT(*) as total_bets,
            SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN result = 'push' THEN 1 ELSE 0 END) as pushes,
            SUM(CASE WHEN result = 'dnp' THEN 1 ELSE 0 END) as dnp,
            SUM(CASE WHEN result = 'void' THEN 1 ELSE 0 END) as void,
            SUM(CASE WHEN result IS NULL THEN 1 ELSE 0 END) as pending,
            AVG(ev_percent) as avg_ev,
            AVG(best_odds) as avg_odds,
            SUM(CASE WHEN result IN ('win', 'loss') THEN profit_loss ELSE 0 END) as total_pl
        FROM bet_log
        WHERE sent_at >= ?
        GROUP BY alert_tier
    """, (cutoff,))

    rows = cursor.fetchall()
    conn.close()

    result = {}
    for row in rows:
        tier = row['alert_tier']
        # Only count actual settled bets (win/loss/push) for win rate
        # DNP/void are excluded from performance metrics
        settled = row['wins'] + row['losses'] + row['pushes']
        result[tier] = {
            'total_bets': row['total_bets'],
            'wins': row['wins'],
            'losses': row['losses'],
            'pushes': row['pushes'],
            'dnp': row['dnp'],
            'void': row['void'],
            'pending': row['pending'],
            'settled': settled,
            'win_rate': round(row['wins'] / settled * 100, 1) if settled > 0 else 0,
            'avg_ev': round(row['avg_ev'], 2) if row['avg_ev'] else 0,
            'avg_odds': int(row['avg_odds']) if row['avg_odds'] else 0,
            'total_pl': round(row['total_pl'], 2) if row['total_pl'] else 0
        }

    return result


def cleanup_duplicates(db_path: str = None) -> int:
    """
    Remove duplicate bets, keeping only the first occurrence per unique_key per game_date.
    Returns the number of duplicates removed.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Find and delete duplicates, keeping the row with the lowest id (first logged)
    cursor.execute("""
        DELETE FROM bet_log
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM bet_log
            GROUP BY unique_key, game_date
        )
    """)

    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    if deleted > 0:
        logger.info(f"Removed {deleted} duplicate bets from bet_log")

    return deleted
