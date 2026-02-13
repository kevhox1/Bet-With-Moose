"""
Main fair value calculation: combines devig + weights.
Ported exactly from calculate_fair_probability() in oddsblaze_bot.py.
"""
from typing import Dict, Optional, Tuple

from services.devig import american_to_probability, two_way_devig, one_way_devig
from services.weights import get_book_weight


def calculate_fair_probability(
    book_odds: Dict[str, Dict],
    opposite_odds: Optional[Dict[str, Dict]] = None,
    market_key: str = '',
) -> Tuple[float, str]:
    """
    Calculate fair probability using MKB V10 methodology.

    HYBRID APPROACH (per-book basis):
        For EACH book:
        - If book has both sides → two-way proportional de-vig
        - If book only has one side → one-way with multiplier
        Then combine via weighted average.

    Returns:
        (fair_probability, calc_type) where calc_type is 'hybrid'|'2-way'|'1-way'|'none'
    """
    if not book_odds:
        return 0.5, 'none'

    weighted_sum = 0.0
    weight_total = 0.0
    two_way_count = 0
    one_way_count = 0

    for book_name, data in book_odds.items():
        odds = data.get('price', 0)
        implied_prob = american_to_probability(odds)

        if implied_prob <= 0:
            continue

        weight = get_book_weight(book_name)

        # Check if this specific book has the opposite side
        has_opposite = opposite_odds and book_name in opposite_odds

        if has_opposite:
            opp_price = opposite_odds[book_name].get('price', 0)
            opp_prob = american_to_probability(opp_price)

            if opp_prob > 0:
                fair_prob = two_way_devig(implied_prob, opp_prob)
                weighted_sum += fair_prob * weight
                weight_total += weight
                two_way_count += 1
                continue

        # ONE-WAY fallback
        fair_prob = one_way_devig(implied_prob, odds, market_key)
        weighted_sum += fair_prob * weight
        weight_total += weight
        one_way_count += 1

    if weight_total > 0:
        final_fair_prob = weighted_sum / weight_total

        if two_way_count > 0 and one_way_count > 0:
            calc_type = 'hybrid'
        elif two_way_count > 0:
            calc_type = '2-way'
        else:
            calc_type = '1-way'

        return final_fair_prob, calc_type

    return 0.5, 'none'
