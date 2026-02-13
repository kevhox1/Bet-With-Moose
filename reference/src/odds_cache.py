"""
NBA Value Alert Bot - Historical Odds Cache
============================================
Stores all raw odds data from every scan for future analysis:
- Line movement tracking
- Closing line value (CLV) analysis
- Market weight calibration
- Time-of-day patterns
- Book accuracy comparison
"""

import sqlite3
import uuid
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Default path - can be overridden
CACHE_DB_PATH = 'odds_cache.db'


def get_cache_connection(db_path: str = None):
    """Get a database connection to the cache."""
    path = db_path or CACHE_DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_cache_database(db_path: str = None):
    """Initialize the odds cache database with all required tables."""
    conn = get_cache_connection(db_path)
    cursor = conn.cursor()

    # Main table: One row per scan session
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scan_sessions (
            scan_id TEXT PRIMARY KEY,
            scan_timestamp TIMESTAMP NOT NULL,
            state TEXT,
            total_events INTEGER,
            total_markets INTEGER,
            total_book_odds INTEGER,
            api_requests_remaining TEXT,
            scan_duration_ms INTEGER
        )
    """)

    # Events/Games table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            home_team TEXT,
            away_team TEXT,
            commence_time TIMESTAMP,
            -- Calculated at scan time
            minutes_to_game INTEGER,
            FOREIGN KEY (scan_id) REFERENCES scan_sessions(scan_id),
            UNIQUE(scan_id, event_id)
        )
    """)

    # Raw odds snapshots: One row per book per outcome per scan
    # This is the most granular data - every single odds line we see
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS odds_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id TEXT NOT NULL,
            scan_timestamp TIMESTAMP NOT NULL,
            -- Event info
            event_id TEXT NOT NULL,
            home_team TEXT,
            away_team TEXT,
            commence_time TIMESTAMP,
            minutes_to_game INTEGER,
            -- Market info
            market_key TEXT NOT NULL,
            market_name TEXT,
            player TEXT,
            line REAL,
            side TEXT,
            -- Book info
            book_key TEXT NOT NULL,
            book_abbrev TEXT NOT NULL,
            odds INTEGER NOT NULL,
            link TEXT,
            -- Calculated values (at scan time)
            fair_prob REAL,
            fair_odds INTEGER,
            ev_pct REAL,
            std_kelly REAL,
            conf_kelly REAL,
            coverage INTEGER,
            calc_type TEXT,
            -- For line movement analysis
            prev_odds INTEGER,
            odds_change INTEGER,
            -- Indexing
            bet_id TEXT NOT NULL,
            FOREIGN KEY (scan_id) REFERENCES scan_sessions(scan_id)
        )
    """)

    # Aggregated market snapshots: One row per unique bet opportunity per scan
    # Contains the "best" odds and fair value calculations
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS market_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id TEXT NOT NULL,
            scan_timestamp TIMESTAMP NOT NULL,
            -- Event info
            event_id TEXT NOT NULL,
            home_team TEXT,
            away_team TEXT,
            commence_time TIMESTAMP,
            minutes_to_game INTEGER,
            -- Market info
            bet_id TEXT NOT NULL,
            market_key TEXT NOT NULL,
            market_name TEXT,
            player TEXT,
            line REAL,
            side TEXT,
            -- Best odds info
            best_odds INTEGER,
            best_books TEXT,
            next_best_odds INTEGER,
            next_best_book TEXT,
            pct_vs_next REAL,
            -- Fair value calculations
            fair_prob REAL,
            fair_odds INTEGER,
            calc_type TEXT,
            coverage INTEGER,
            -- EV metrics
            ev_pct REAL,
            std_kelly REAL,
            conf_kelly REAL,
            -- Alert tier (if any)
            alert_tier TEXT,
            -- All book odds as JSON for full reconstruction
            all_book_odds JSON,
            -- Line movement
            prev_best_odds INTEGER,
            best_odds_change INTEGER,
            FOREIGN KEY (scan_id) REFERENCES scan_sessions(scan_id),
            UNIQUE(scan_id, bet_id)
        )
    """)

    # Book performance tracking: aggregate stats per book
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS book_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            book_abbrev TEXT NOT NULL,
            total_lines INTEGER DEFAULT 0,
            lines_with_best_odds INTEGER DEFAULT 0,
            avg_odds_vs_fair REAL,
            avg_ev_when_best REAL,
            UNIQUE(date, book_abbrev)
        )
    """)

    # Closing line tracking: record final odds before game starts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS closing_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            bet_id TEXT NOT NULL,
            closing_timestamp TIMESTAMP,
            closing_best_odds INTEGER,
            closing_fair_odds INTEGER,
            closing_ev_pct REAL,
            -- Link to the bet we actually took (if any)
            bet_taken_odds INTEGER,
            bet_taken_timestamp TIMESTAMP,
            clv_pct REAL,
            UNIQUE(event_id, bet_id)
        )
    """)

    # Create indexes for common queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_odds_scan_id ON odds_snapshots(scan_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_odds_timestamp ON odds_snapshots(scan_timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_odds_book ON odds_snapshots(book_abbrev)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_odds_bet_id ON odds_snapshots(bet_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_odds_event ON odds_snapshots(event_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_odds_player ON odds_snapshots(player)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_odds_market ON odds_snapshots(market_key)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_scan_id ON market_snapshots(scan_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_timestamp ON market_snapshots(scan_timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_bet_id ON market_snapshots(bet_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_event ON market_snapshots(event_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_player ON market_snapshots(player)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_tier ON market_snapshots(alert_tier)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_closing_event ON closing_lines(event_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_closing_bet ON closing_lines(bet_id)")

    conn.commit()
    conn.close()
    logger.info("Odds cache database initialized")


def start_scan_session(state: str = None, db_path: str = None) -> str:
    """Start a new scan session and return the scan_id."""
    scan_id = str(uuid.uuid4())
    conn = get_cache_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO scan_sessions (scan_id, scan_timestamp, state)
        VALUES (?, ?, ?)
    """, (scan_id, datetime.now(timezone.utc).isoformat(), state))

    conn.commit()
    conn.close()
    return scan_id


def complete_scan_session(
    scan_id: str,
    total_events: int,
    total_markets: int,
    total_book_odds: int,
    api_remaining: str = None,
    scan_duration_ms: int = None,
    db_path: str = None
):
    """Update scan session with final stats."""
    conn = get_cache_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE scan_sessions
        SET total_events = ?,
            total_markets = ?,
            total_book_odds = ?,
            api_requests_remaining = ?,
            scan_duration_ms = ?
        WHERE scan_id = ?
    """, (total_events, total_markets, total_book_odds, api_remaining, scan_duration_ms, scan_id))

    conn.commit()
    conn.close()


def cache_event(
    scan_id: str,
    event_id: str,
    home_team: str,
    away_team: str,
    commence_time: datetime,
    db_path: str = None
):
    """Cache event/game info."""
    conn = get_cache_connection(db_path)
    cursor = conn.cursor()

    now = datetime.now(timezone.utc)
    minutes_to_game = int((commence_time - now).total_seconds() / 60) if commence_time > now else 0

    cursor.execute("""
        INSERT OR REPLACE INTO events
        (scan_id, event_id, home_team, away_team, commence_time, minutes_to_game)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (scan_id, event_id, home_team, away_team, commence_time.isoformat(), minutes_to_game))

    conn.commit()
    conn.close()


def cache_odds_snapshot(
    scan_id: str,
    scan_timestamp: datetime,
    event_id: str,
    home_team: str,
    away_team: str,
    commence_time: datetime,
    market_key: str,
    market_name: str,
    player: str,
    line: float,
    side: str,
    book_key: str,
    book_abbrev: str,
    odds: int,
    link: str = None,
    fair_prob: float = None,
    fair_odds: int = None,
    ev_pct: float = None,
    std_kelly: float = None,
    conf_kelly: float = None,
    coverage: int = None,
    calc_type: str = None,
    bet_id: str = None,
    db_path: str = None
):
    """Cache a single odds snapshot (one book, one outcome)."""
    conn = get_cache_connection(db_path)
    cursor = conn.cursor()

    now = datetime.now(timezone.utc)
    minutes_to_game = int((commence_time - now).total_seconds() / 60) if commence_time > now else 0

    # Look up previous odds for this bet_id + book
    cursor.execute("""
        SELECT odds FROM odds_snapshots
        WHERE bet_id = ? AND book_abbrev = ?
        ORDER BY scan_timestamp DESC LIMIT 1
    """, (bet_id, book_abbrev))
    prev_row = cursor.fetchone()
    prev_odds = prev_row['odds'] if prev_row else None
    odds_change = (odds - prev_odds) if prev_odds else None

    cursor.execute("""
        INSERT INTO odds_snapshots (
            scan_id, scan_timestamp, event_id, home_team, away_team,
            commence_time, minutes_to_game, market_key, market_name,
            player, line, side, book_key, book_abbrev, odds, link,
            fair_prob, fair_odds, ev_pct, std_kelly, conf_kelly,
            coverage, calc_type, prev_odds, odds_change, bet_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        scan_id, scan_timestamp.isoformat(), event_id, home_team, away_team,
        commence_time.isoformat(), minutes_to_game, market_key, market_name,
        player, line, side, book_key, book_abbrev, odds, link,
        fair_prob, fair_odds, ev_pct, std_kelly, conf_kelly,
        coverage, calc_type, prev_odds, odds_change, bet_id
    ))

    conn.commit()
    conn.close()


def cache_market_snapshot(
    scan_id: str,
    scan_timestamp: datetime,
    event_id: str,
    home_team: str,
    away_team: str,
    commence_time: datetime,
    bet_id: str,
    market_key: str,
    market_name: str,
    player: str,
    line: float,
    side: str,
    best_odds: int,
    best_books: str,
    next_best_odds: int = None,
    next_best_book: str = None,
    pct_vs_next: float = None,
    fair_prob: float = None,
    fair_odds: int = None,
    calc_type: str = None,
    coverage: int = None,
    ev_pct: float = None,
    std_kelly: float = None,
    conf_kelly: float = None,
    alert_tier: str = None,
    all_book_odds: Dict = None,
    db_path: str = None
):
    """Cache aggregated market snapshot (best odds, fair value for a betting opportunity)."""
    conn = get_cache_connection(db_path)
    cursor = conn.cursor()

    now = datetime.now(timezone.utc)
    minutes_to_game = int((commence_time - now).total_seconds() / 60) if commence_time > now else 0

    # Look up previous best odds for this bet_id
    cursor.execute("""
        SELECT best_odds FROM market_snapshots
        WHERE bet_id = ?
        ORDER BY scan_timestamp DESC LIMIT 1
    """, (bet_id,))
    prev_row = cursor.fetchone()
    prev_best_odds = prev_row['best_odds'] if prev_row else None
    best_odds_change = (best_odds - prev_best_odds) if prev_best_odds else None

    cursor.execute("""
        INSERT OR REPLACE INTO market_snapshots (
            scan_id, scan_timestamp, event_id, home_team, away_team,
            commence_time, minutes_to_game, bet_id, market_key, market_name,
            player, line, side, best_odds, best_books, next_best_odds,
            next_best_book, pct_vs_next, fair_prob, fair_odds, calc_type,
            coverage, ev_pct, std_kelly, conf_kelly, alert_tier,
            all_book_odds, prev_best_odds, best_odds_change
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        scan_id, scan_timestamp.isoformat(), event_id, home_team, away_team,
        commence_time.isoformat(), minutes_to_game, bet_id, market_key, market_name,
        player, line, side, best_odds, best_books, next_best_odds,
        next_best_book, pct_vs_next, fair_prob, fair_odds, calc_type,
        coverage, ev_pct, std_kelly, conf_kelly, alert_tier,
        json.dumps(all_book_odds) if all_book_odds else None,
        prev_best_odds, best_odds_change
    ))

    conn.commit()
    conn.close()


def batch_cache_odds(snapshots: List[Dict], db_path: str = None):
    """Batch insert multiple odds snapshots for efficiency.

    NOTE: For performance, we skip prev_odds lookup during insert.
    Line movement can be calculated later via SQL query when needed.
    """
    if not snapshots:
        return

    conn = get_cache_connection(db_path)
    cursor = conn.cursor()

    # Prepare batch insert - skip prev_odds lookup for speed
    rows = []
    for s in snapshots:
        rows.append((
            s['scan_id'], s['scan_timestamp'], s['event_id'], s['home_team'], s['away_team'],
            s['commence_time'], s['minutes_to_game'], s['market_key'], s['market_name'],
            s['player'], s['line'], s['side'], s['book_key'], s['book_abbrev'],
            s['odds'], s.get('link'), s.get('fair_prob'), s.get('fair_odds'),
            s.get('ev_pct'), s.get('std_kelly'), s.get('conf_kelly'),
            s.get('coverage'), s.get('calc_type'), None, None, s['bet_id']
        ))

    cursor.executemany("""
        INSERT INTO odds_snapshots (
            scan_id, scan_timestamp, event_id, home_team, away_team,
            commence_time, minutes_to_game, market_key, market_name,
            player, line, side, book_key, book_abbrev, odds, link,
            fair_prob, fair_odds, ev_pct, std_kelly, conf_kelly,
            coverage, calc_type, prev_odds, odds_change, bet_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)

    conn.commit()
    conn.close()
    logger.debug(f"Batch cached {len(rows)} odds snapshots")


def batch_cache_markets(markets: List[Dict], db_path: str = None):
    """Batch insert multiple market snapshots for efficiency.

    NOTE: For performance, we skip prev_best_odds lookup during insert.
    Line movement can be calculated later via SQL query when needed.
    """
    if not markets:
        return

    conn = get_cache_connection(db_path)
    cursor = conn.cursor()

    # Skip prev_odds lookup for speed - prepare batch insert directly
    rows = []
    for m in markets:
        rows.append((
            m['scan_id'], m['scan_timestamp'], m['event_id'], m['home_team'], m['away_team'],
            m['commence_time'], m['minutes_to_game'], m['bet_id'], m['market_key'], m['market_name'],
            m['player'], m['line'], m['side'], m['best_odds'], m['best_books'],
            m.get('next_best_odds'), m.get('next_best_book'), m.get('pct_vs_next'),
            m.get('fair_prob'), m.get('fair_odds'), m.get('calc_type'), m.get('coverage'),
            m.get('ev_pct'), m.get('std_kelly'), m.get('conf_kelly'), m.get('alert_tier'),
            json.dumps(m.get('all_book_odds')) if m.get('all_book_odds') else None,
            None, None  # prev_best_odds, best_odds_change - calculated later if needed
        ))

    cursor.executemany("""
        INSERT OR REPLACE INTO market_snapshots (
            scan_id, scan_timestamp, event_id, home_team, away_team,
            commence_time, minutes_to_game, bet_id, market_key, market_name,
            player, line, side, best_odds, best_books, next_best_odds,
            next_best_book, pct_vs_next, fair_prob, fair_odds, calc_type,
            coverage, ev_pct, std_kelly, conf_kelly, alert_tier,
            all_book_odds, prev_best_odds, best_odds_change
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)

    conn.commit()
    conn.close()
    logger.debug(f"Batch cached {len(rows)} market snapshots")


def update_closing_line(
    event_id: str,
    bet_id: str,
    closing_best_odds: int,
    closing_fair_odds: int,
    closing_ev_pct: float,
    db_path: str = None
):
    """Record closing line for CLV analysis."""
    conn = get_cache_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO closing_lines
        (event_id, bet_id, closing_timestamp, closing_best_odds, closing_fair_odds, closing_ev_pct)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (event_id, bet_id, datetime.now(timezone.utc).isoformat(),
          closing_best_odds, closing_fair_odds, closing_ev_pct))

    conn.commit()
    conn.close()


def record_bet_taken(
    event_id: str,
    bet_id: str,
    odds_taken: int,
    db_path: str = None
):
    """Record that we took a bet (for CLV calculation later)."""
    conn = get_cache_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO closing_lines (event_id, bet_id, bet_taken_odds, bet_taken_timestamp)
        VALUES (?, ?, ?, ?)
    """, (event_id, bet_id, odds_taken, datetime.now(timezone.utc).isoformat()))

    # If row already exists, just update the bet_taken fields
    cursor.execute("""
        UPDATE closing_lines
        SET bet_taken_odds = ?, bet_taken_timestamp = ?
        WHERE event_id = ? AND bet_id = ?
    """, (odds_taken, datetime.now(timezone.utc).isoformat(), event_id, bet_id))

    conn.commit()
    conn.close()


def cleanup_old_data(days_to_keep: int = 30, db_path: str = None):
    """Remove data older than specified days."""
    conn = get_cache_connection(db_path)
    cursor = conn.cursor()

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_to_keep)).isoformat()

    cursor.execute("DELETE FROM odds_snapshots WHERE scan_timestamp < ?", (cutoff,))
    odds_deleted = cursor.rowcount

    cursor.execute("DELETE FROM market_snapshots WHERE scan_timestamp < ?", (cutoff,))
    markets_deleted = cursor.rowcount

    cursor.execute("DELETE FROM events WHERE scan_id IN (SELECT scan_id FROM scan_sessions WHERE scan_timestamp < ?)", (cutoff,))
    cursor.execute("DELETE FROM scan_sessions WHERE scan_timestamp < ?", (cutoff,))
    sessions_deleted = cursor.rowcount

    conn.commit()
    conn.close()

    logger.info(f"Cleanup: removed {odds_deleted} odds snapshots, {markets_deleted} market snapshots, {sessions_deleted} scan sessions older than {days_to_keep} days")
    return {'odds_deleted': odds_deleted, 'markets_deleted': markets_deleted, 'sessions_deleted': sessions_deleted}


def get_cache_stats(db_path: str = None) -> Dict:
    """Get statistics about the cache."""
    conn = get_cache_connection(db_path)
    cursor = conn.cursor()

    stats = {}

    cursor.execute("SELECT COUNT(*) as count FROM scan_sessions")
    stats['total_scans'] = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) as count FROM odds_snapshots")
    stats['total_odds_snapshots'] = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) as count FROM market_snapshots")
    stats['total_market_snapshots'] = cursor.fetchone()['count']

    cursor.execute("SELECT MIN(scan_timestamp) as oldest, MAX(scan_timestamp) as newest FROM scan_sessions")
    row = cursor.fetchone()
    stats['oldest_scan'] = row['oldest']
    stats['newest_scan'] = row['newest']

    cursor.execute("SELECT COUNT(DISTINCT book_abbrev) as count FROM odds_snapshots")
    stats['unique_books'] = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(DISTINCT player) as count FROM odds_snapshots")
    stats['unique_players'] = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(DISTINCT market_key) as count FROM odds_snapshots")
    stats['unique_markets'] = cursor.fetchone()['count']

    # Database file size
    cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
    row = cursor.fetchone()
    stats['db_size_bytes'] = row['size'] if row else 0
    stats['db_size_mb'] = round(stats['db_size_bytes'] / (1024 * 1024), 2)

    conn.close()
    return stats


def export_to_csv(output_dir: str, start_date: str = None, end_date: str = None, db_path: str = None):
    """Export cache data to CSV files for analysis."""
    import csv
    import os

    conn = get_cache_connection(db_path)
    cursor = conn.cursor()

    os.makedirs(output_dir, exist_ok=True)

    # Build date filter
    date_filter = ""
    params = []
    if start_date:
        date_filter += " AND scan_timestamp >= ?"
        params.append(start_date)
    if end_date:
        date_filter += " AND scan_timestamp <= ?"
        params.append(end_date)

    # Export odds snapshots
    cursor.execute(f"SELECT * FROM odds_snapshots WHERE 1=1 {date_filter}", params)
    rows = cursor.fetchall()

    if rows:
        odds_file = os.path.join(output_dir, 'odds_snapshots.csv')
        with open(odds_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([desc[0] for desc in cursor.description])
            writer.writerows(rows)
        logger.info(f"Exported {len(rows)} odds snapshots to {odds_file}")

    # Export market snapshots
    cursor.execute(f"SELECT * FROM market_snapshots WHERE 1=1 {date_filter}", params)
    rows = cursor.fetchall()

    if rows:
        markets_file = os.path.join(output_dir, 'market_snapshots.csv')
        with open(markets_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([desc[0] for desc in cursor.description])
            writer.writerows(rows)
        logger.info(f"Exported {len(rows)} market snapshots to {markets_file}")

    conn.close()


def get_line_movement(bet_id: str, hours_back: int = 24, db_path: str = None) -> List[Dict]:
    """Get line movement history for a specific bet with calculated changes."""
    conn = get_cache_connection(db_path)
    cursor = conn.cursor()

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).isoformat()

    # Use window function to calculate line movement on the fly
    cursor.execute("""
        SELECT
            scan_timestamp,
            book_abbrev,
            odds,
            LAG(odds) OVER (PARTITION BY book_abbrev ORDER BY scan_timestamp) as prev_odds,
            odds - LAG(odds) OVER (PARTITION BY book_abbrev ORDER BY scan_timestamp) as odds_change
        FROM odds_snapshots
        WHERE bet_id = ? AND scan_timestamp >= ?
        ORDER BY scan_timestamp ASC
    """, (bet_id, cutoff))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_book_accuracy_stats(days_back: int = 7, db_path: str = None) -> List[Dict]:
    """Get book accuracy statistics - how often each book has best odds."""
    conn = get_cache_connection(db_path)
    cursor = conn.cursor()

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()

    cursor.execute("""
        SELECT
            book_abbrev,
            COUNT(*) as total_lines,
            SUM(CASE WHEN odds = (
                SELECT MAX(o2.odds) FROM odds_snapshots o2
                WHERE o2.bet_id = odds_snapshots.bet_id
                AND o2.scan_id = odds_snapshots.scan_id
            ) THEN 1 ELSE 0 END) as times_best,
            AVG(ev_pct) as avg_ev
        FROM odds_snapshots
        WHERE scan_timestamp >= ? AND ev_pct IS NOT NULL
        GROUP BY book_abbrev
        ORDER BY times_best DESC
    """, (cutoff,))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]
