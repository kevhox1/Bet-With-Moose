"""
Kelly criterion and EV calculations.
Ported exactly from oddsblaze_bot.py.
"""


def calculate_ev_percentage(fair_prob: float, best_odds: int) -> float:
    """Calculate expected value percentage."""
    if fair_prob <= 0 or best_odds == 0:
        return 0.0

    if best_odds > 0:
        decimal_odds = (best_odds / 100) + 1
    else:
        decimal_odds = (100 / abs(best_odds)) + 1

    ev = (fair_prob * decimal_odds) - 1
    return ev * 100


def calculate_kelly(edge: float, decimal_odds: float, fraction: float = 0.25) -> float:
    """Calculate Kelly stake (Quarter Kelly by default). Returns units."""
    if decimal_odds <= 1 or edge <= 0:
        return 0.0
    kelly_full = edge / (decimal_odds - 1)
    kelly_fractional = kelly_full * fraction
    return kelly_fractional * 100
