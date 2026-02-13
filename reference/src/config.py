"""
NBA Value Alert Bot - Configuration
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Telegram Settings
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# TheOddsAPI Settings
THEODDSAPI_KEY = os.getenv("THEODDSAPI_KEY")

# State for bet links
STATE = os.getenv("STATE", "ny")

# Scanning Settings
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "180"))  # 3 minutes

# Active hours (Eastern Time) - tuple of (start_hour, end_hour)
# Scanner only runs during these hours, auto-pauses outside this window
# Default: 8AM to midnight EST (when NBA games typically occur)
ACTIVE_HOURS_START = int(os.getenv("ACTIVE_HOURS_START", "8"))   # 8 AM EST
ACTIVE_HOURS_END = int(os.getenv("ACTIVE_HOURS_END", "24"))      # Midnight EST

# Re-alert thresholds
EV_IMPROVEMENT_THRESHOLD = float(os.getenv("EV_IMPROVEMENT_THRESHOLD", "3.0"))    # Re-alert if EV improved by 3%+
MIN_REALERT_MINUTES = int(os.getenv("MIN_REALERT_MINUTES", "30"))                 # Never re-alert within 30 minutes

# Alert tiers to auto-send
AUTO_ALERT_TIERS = ['FIRE', 'VALUE_LONGSHOT', 'OUTLIER']

# Maximum alerts per tier per scan (0 = unlimited)
MAX_ALERTS_PER_TIER = {
    'FIRE': 0,           # Unlimited
    'VALUE_LONGSHOT': 5, # Max 5 per scan
    'OUTLIER': 5         # Max 5 per scan
}

# Valid US states for bet links
VALID_STATES = [
    'az', 'co', 'ct', 'dc', 'il', 'in', 'ia', 'ks', 'ky', 'la',
    'ma', 'md', 'mi', 'mo', 'nc', 'nh', 'nj', 'ny', 'oh', 'or',
    'pa', 'tn', 'va', 'vt', 'wv', 'wy'
]

# =============================================================================
# LEGAL SPORTSBOOKS BY STATE
# =============================================================================
# Book abbreviations: DK=DraftKings, FD=FanDuel, MG=BetMGM, CZ=Caesars,
# ES=ESPN Bet, FN=Fanatics, BR=BetRivers, RK=Hard Rock, BB=Bally Bet,
# BP=BetParx, CI=Circa, RB=Rebet, BO=BetOnline, FL=Fliff
# EXCLUDED (never send alerts): PN=Pinnacle, BV=Bovada

# Books available in ALL states (offshore but commonly used)
UNIVERSAL_BOOKS = ['FL']

STATE_LEGAL_BOOKS = {
    # Arizona - Wide availability
    'az': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'RK', 'BB', 'FL'],

    # Colorado - Wide availability
    'co': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'BB', 'CI', 'FL'],

    # Connecticut - Limited (tribal partnerships only)
    'ct': ['DK', 'FD', 'FN', 'FL'],

    # Washington DC - Limited
    'dc': ['DK', 'FD', 'MG', 'CZ', 'FL'],

    # Illinois - Wide availability
    'il': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'BB', 'FL'],

    # Indiana - Wide availability
    'in': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'RK', 'CI', 'FL'],

    # Iowa - Wide availability
    'ia': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'RK', 'BB', 'FL'],

    # Kansas - Wide availability
    'ks': ['DK', 'FD', 'MG', 'CZ', 'ES', 'BR', 'RK', 'BB', 'CI', 'FL'],

    # Kentucky - Limited
    'ky': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'FL'],

    # Louisiana - Wide availability
    'la': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'FL'],

    # Massachusetts - Limited
    'ma': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'FL'],

    # Maryland - Wide availability
    'md': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'BB', 'BP', 'FL'],

    # Michigan - Wide availability
    'mi': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'BB', 'RK', 'FL'],

    # Missouri - New market (Dec 2025)
    'mo': ['DK', 'FD', 'MG', 'CZ', 'FN', 'CI', 'FL'],

    # North Carolina - Wide availability
    'nc': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'BB', 'FL'],

    # New Hampshire - DraftKings exclusive
    'nh': ['DK', 'FL'],

    # New Jersey - Wide availability (most mature market)
    'nj': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'RK', 'BP', 'FL'],

    # New York - Wide availability
    'ny': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'FL'],

    # Ohio - Wide availability
    'oh': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'RK', 'BB', 'FL'],

    # Oregon - DraftKings only (state lottery partner)
    'or': ['DK', 'FL'],

    # Pennsylvania - Wide availability
    'pa': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'BP', 'FL'],

    # Tennessee - Online only, wide availability
    'tn': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'RK', 'FL'],

    # Virginia - Wide availability
    'va': ['DK', 'FD', 'MG', 'CZ', 'ES', 'FN', 'BR', 'RK', 'BB', 'FL'],

    # Vermont - Limited (new market Jan 2025)
    'vt': ['DK', 'FD', 'FN', 'FL'],

    # West Virginia - Limited
    'wv': ['DK', 'FD', 'MG', 'CZ', 'FN', 'BR', 'FL'],

    # Wyoming - Online only, limited
    'wy': ['DK', 'FD', 'MG', 'CZ', 'FL'],
}

# Books to ALWAYS exclude from alerts (even if they have best odds)
EXCLUDED_BOOKS = ['PN', 'BV', 'BO']

# Full book names for display
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
}

# Database file path
DATABASE_PATH = os.getenv("DATABASE_PATH", "alerts.db")

# Logging
LOG_FILE = os.getenv("LOG_FILE", "bot.log")
