"""
Configuration: weights, multipliers, thresholds.
Extracted from OddsBlaze bot V10 Pinnacle-Optimized methodology.
"""

# Book abbreviation mapping (OddsBlaze lowercase -> abbreviation)
BOOK_ABBREV_MAP = {
    'draftkings': 'DK',
    'fanduel': 'FD',
    'betmgm': 'MG',
    'caesars': 'CZ',
    'betrivers': 'BR',
    'fanatics': 'FN',
    'betparx': 'BP',
    'fliff': 'FL',
    'thescore': 'TS',
    'pinnacle': 'PN',
    'circa': 'CI',
    'bet365': 'B3',
    'bally-bet': 'BB',
    'hard-rock': 'HR',
    'prophetx': 'PX',
    'fanduel-yourway': 'FDYW',
}

# Global weights (V10 Pinnacle-Optimized)
GLOBAL_WEIGHTS = {
    'DK': 0.2027,
    'FD': 0.1599,
    'MG': 0.1580,
    'PN': 0.1328,
    'ES': 0.0883,
    'RK': 0.0828,
    'CZ': 0.0742,
    'BO': 0.0412,
    'BB': 0.0096,
    'BR': 0.0096,
    'FL': 0.0096,
    'FN': 0.0096,
    'RB': 0.0048,
    'BP': 0.0048,
    'CI': 0.0000,
    'TS': 0.0048,
    'B3': 0.0000,
    'HR': 0.0096,
    'KA': 0.0000,
    'NV': 0.0000,
    'PX': 0.0000,
    'BY': 0.0000,
    'FDYW': 0.0000,
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

# Market-specific multipliers for short/medium odds
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

# Longshot-specific multipliers (+1000-2999)
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

# Extreme longshot multipliers (+3000+)
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

# Confidence multipliers based on book coverage
CONFIDENCE_MULTIPLIERS = {
    1: 0.25, 2: 0.35, 3: 0.47, 4: 0.47, 5: 0.53,
    6: 0.56, 7: 0.62, 8: 0.70, 9: 0.72, 10: 0.81,
    11: 0.81, 12: 0.91, 13: 0.96, 14: 1.00, 15: 1.00,
}

# Sharp books excluded from best odds selection
SHARP_BOOKS = {'pinnacle', 'circa'}

# Default minimum weight for unknown books
DEFAULT_WEIGHT = 0.01
