"""
NBA Value Scanner Test Bot - Configuration
==========================================
Extended configuration for SportsGameOdds test bot.
Includes additional sportsbooks: bet365, novig, prophetexchange
"""

import os
from dotenv import load_dotenv

# Load from .env.test if exists
if os.path.exists('.env.test'):
    load_dotenv('.env.test')
else:
    load_dotenv()

# =============================================================================
# TELEGRAM SETTINGS (TEST CHANNEL)
# =============================================================================
TEST_TELEGRAM_BOT_TOKEN = os.getenv("TEST_TELEGRAM_BOT_TOKEN")
TEST_TELEGRAM_CHAT_ID = os.getenv("TEST_TELEGRAM_CHAT_ID")

# =============================================================================
# SPORTSGAMEODDS SETTINGS
# =============================================================================
# API Key - can be overridden by env var
SPORTSGAMEODDS_API_KEY = os.getenv("SPORTSGAMEODDS_API_KEY", "7546525eada0352b926e60dbc6c42cb0")
SPORTSGAMEODDS_MODE = os.getenv("SPORTSGAMEODDS_MODE", "rest")

# =============================================================================
# STATE SETTINGS
# =============================================================================
STATE = os.getenv("STATE", "ny")

# Scanning Settings
SCAN_INTERVAL_SECONDS = int(os.getenv("TEST_SCAN_INTERVAL_SECONDS", "180"))

# Active hours
ACTIVE_HOURS_START = int(os.getenv("ACTIVE_HOURS_START", "8"))
ACTIVE_HOURS_END = int(os.getenv("ACTIVE_HOURS_END", "24"))

# Alert Settings
EV_IMPROVEMENT_THRESHOLD = float(os.getenv("EV_IMPROVEMENT_THRESHOLD", "3.0"))
MIN_REALERT_MINUTES = int(os.getenv("MIN_REALERT_MINUTES", "30"))

AUTO_ALERT_TIERS = ['FIRE', 'VALUE_LONGSHOT', 'OUTLIER']
MAX_ALERTS_PER_TIER = {
    'FIRE': 0,
    'VALUE_LONGSHOT': 5,
    'OUTLIER': 5
}

# =============================================================================
# VALID STATES
# =============================================================================
VALID_STATES = [
    'az', 'co', 'ct', 'dc', 'il', 'in', 'ia', 'ks', 'ky', 'la',
    'ma', 'md', 'mi', 'mo', 'nc', 'nh', 'nj', 'ny', 'oh', 'or',
    'pa', 'tn', 'va', 'vt', 'wv', 'wy'
]

# =============================================================================
# SPORTSBOOK CONFIGURATION
# =============================================================================
# Book abbreviations:
# DK=DraftKings, FD=FanDuel, MG=BetMGM, CZ=Caesars, ES=ESPN Bet, FN=Fanatics
# BR=BetRivers, RK=Hard Rock, BB=Bally Bet, BP=BetParx, CI=Circa
# B3=bet365 (NEW), NV=Novig (NEW), PX=ProphetExchange (NEW)
# PN=Pinnacle (sharp, excluded from alerts), BV=Bovada, BO=BetOnline

# Universal books available everywhere (includes offshore/international)
UNIVERSAL_BOOKS = ['FL']

# Books available via exchanges (shown for all states as betting destinations)
EXCHANGE_BOOKS = ['NV', 'PX', 'KA', 'BY']

# bet365 availability - note: bet365 is not licensed in most US states
# but may be available via SportsGameOdds for comparison/fair value
BET365_AVAILABLE = ['B3']  # Available for all states via API (international lines)

# =============================================================================
# LEGAL SPORTSBOOKS BY STATE (Extended for Test Bot)
# =============================================================================
# Same as production but with exchanges added for visibility

STATE_LEGAL_BOOKS = {
    # Arizona
    'az': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'RK', 'BB', 'FL'] + EXCHANGE_BOOKS,

    # Colorado
    'co': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'BB', 'CI', 'FL'] + EXCHANGE_BOOKS,

    # Connecticut
    'ct': ['DK', 'FD', 'FN', 'FL'] + EXCHANGE_BOOKS,

    # Washington DC
    'dc': ['DK', 'FD', 'MG', 'CZ', 'FL'] + EXCHANGE_BOOKS,

    # Illinois
    'il': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'BB', 'FL'] + EXCHANGE_BOOKS,

    # Indiana
    'in': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'RK', 'CI', 'FL'] + EXCHANGE_BOOKS,

    # Iowa
    'ia': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'RK', 'BB', 'FL'] + EXCHANGE_BOOKS,

    # Kansas
    'ks': ['DK', 'FD', 'MG', 'CZ', 'ES', 'BR', 'RK', 'BB', 'CI', 'FL'] + EXCHANGE_BOOKS,

    # Kentucky
    'ky': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'FL'] + EXCHANGE_BOOKS,

    # Louisiana
    'la': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'FL'] + EXCHANGE_BOOKS,

    # Massachusetts
    'ma': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'FL'] + EXCHANGE_BOOKS,

    # Maryland
    'md': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'BB', 'BP', 'FL'] + EXCHANGE_BOOKS,

    # Michigan
    'mi': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'BB', 'RK', 'FL'] + EXCHANGE_BOOKS,

    # Missouri
    'mo': ['DK', 'FD', 'MG', 'CZ', 'FN', 'CI', 'FL'] + EXCHANGE_BOOKS,

    # North Carolina
    'nc': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'BB', 'FL'] + EXCHANGE_BOOKS,

    # New Hampshire
    'nh': ['DK', 'FL'] + EXCHANGE_BOOKS,

    # New Jersey
    'nj': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'RK', 'BP', 'FL'] + EXCHANGE_BOOKS,

    # New York
    'ny': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'FL'] + EXCHANGE_BOOKS,

    # Ohio
    'oh': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'RK', 'BB', 'FL'] + EXCHANGE_BOOKS,

    # Oregon
    'or': ['DK', 'FL'] + EXCHANGE_BOOKS,

    # Pennsylvania
    'pa': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'BP', 'FL'] + EXCHANGE_BOOKS,

    # Tennessee
    'tn': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'RK', 'FL'] + EXCHANGE_BOOKS,

    # Virginia
    'va': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'RK', 'BB', 'FL'] + EXCHANGE_BOOKS,

    # Vermont
    'vt': ['DK', 'FD', 'FN', 'FL'] + EXCHANGE_BOOKS,

    # West Virginia
    'wv': ['DK', 'FD', 'MG', 'CZ', 'FN', 'BR', 'FL'] + EXCHANGE_BOOKS,

    # Wyoming
    'wy': ['DK', 'FD', 'MG', 'CZ', 'FL'] + EXCHANGE_BOOKS,
}

# =============================================================================
# EXCLUDED BOOKS
# =============================================================================
# Books to ALWAYS exclude from alerts (even if they have best odds)
# These are used for fair value calculation only
# Books excluded from alerts (sharp books used for fair value only)
# Note: bet365 (B3) is available for alerts since some users can access it
EXCLUDED_BOOKS = ['PN']  # Pinnacle only - too sharp, used for fair value only

# =============================================================================
# FULL BOOK NAMES
# =============================================================================
BOOK_FULL_NAMES = {
    'DK': 'DraftKings',
    'FD': 'FanDuel',
    'MG': 'BetMGM',
    'CZ': 'Caesars',
    'ES': 'ESPN Bet',
    'FN': 'Fanatics',
    'BR': 'BetRivers',
    'RK': 'Hard Rock',
    'BB': 'Bally Bet',
    'BP': 'BetParx',
    'CI': 'Circa',
    'RB': 'Rebet',
    'BO': 'BetOnline',
    'FL': 'Fliff',
    'PN': 'Pinnacle',
    'BV': 'Bovada',
    # NEW BOOKS
    'B3': 'bet365',
    'NV': 'Novig',
    'PX': 'ProphetX',
    'KA': 'Kalshi',
    'BY': 'BetOpenly',
}

# =============================================================================
# DATABASE
# =============================================================================
DATABASE_PATH = os.getenv("TEST_DATABASE_PATH", "test_alerts.db")
LOG_FILE = os.getenv("TEST_LOG_FILE", "test_bot.log")
