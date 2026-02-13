"""
De-vig calculations: 2-way proportional and 1-way multiplier.
Ported exactly from oddsblaze_bot.py.
"""
from config import (
    ONE_WAY_MULTIPLIERS,
    MARKET_MULTIPLIERS,
    LONGSHOT_MARKET_MULTIPLIERS,
    EXTREME_LONGSHOT_MULTIPLIERS,
)


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


def get_one_way_multiplier(avg_odds: float) -> float:
    """Get the vig-removal multiplier based on average odds level."""
    if avg_odds < -200:
        return ONE_WAY_MULTIPLIERS[0]
    elif avg_odds < -110:
        return ONE_WAY_MULTIPLIERS[1]
    elif avg_odds <= 110:
        return ONE_WAY_MULTIPLIERS[2]
    elif avg_odds <= 200:
        return ONE_WAY_MULTIPLIERS[3]
    elif avg_odds <= 400:
        return ONE_WAY_MULTIPLIERS[4]
    elif avg_odds <= 700:
        return ONE_WAY_MULTIPLIERS[5]
    elif avg_odds <= 1000:
        return ONE_WAY_MULTIPLIERS[6]
    elif avg_odds <= 2000:
        return ONE_WAY_MULTIPLIERS[7]
    elif avg_odds <= 5000:
        return ONE_WAY_MULTIPLIERS[8]
    else:
        return ONE_WAY_MULTIPLIERS[9]


def two_way_devig(implied_prob: float, opposite_prob: float) -> float:
    """Proportional de-vig: fair_prob = my_prob / (my_prob + opp_prob)."""
    if implied_prob <= 0 or opposite_prob <= 0:
        return 0.0
    return implied_prob / (implied_prob + opposite_prob)


def one_way_devig(implied_prob: float, odds: int, market_key: str) -> float:
    """One-way de-vig using multiplier based on odds level and market type."""
    odds_multiplier = get_one_way_multiplier(odds)

    # Extreme longshots (+3000+)
    if odds >= 3000:
        for market_pattern, mult in EXTREME_LONGSHOT_MULTIPLIERS.items():
            if market_pattern in market_key:
                return implied_prob * mult
        return implied_prob * odds_multiplier

    # Longshots (+1000 to +2999)
    if odds >= 1000:
        for market_pattern, mult in LONGSHOT_MARKET_MULTIPLIERS.items():
            if market_pattern in market_key:
                return implied_prob * mult
        return implied_prob * odds_multiplier

    # Non-longshots: use higher (more conservative) of market vs odds multiplier
    for market_pattern, mult in MARKET_MULTIPLIERS.items():
        if market_pattern in market_key:
            return implied_prob * max(mult, odds_multiplier)

    return implied_prob * odds_multiplier
