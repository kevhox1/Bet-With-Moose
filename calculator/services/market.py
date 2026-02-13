"""
Market data processing: find best odds, compute results per market.
"""
from typing import Dict, List, Optional
from services.devig import american_to_probability, probability_to_american
from services.fair_value import calculate_fair_probability
from services.kelly import calculate_ev_percentage, calculate_kelly
from services.weights import get_confidence_multiplier
from config import SHARP_BOOKS


def process_market(market: dict) -> dict:
    """Process a single market request and return computed results."""
    book_odds = market.get('book_odds', {})
    opposite_odds = market.get('opposite_odds', None)
    market_key = market.get('market_key', '')

    if not book_odds:
        return _empty_result(market)

    # Find best retail odds
    sorted_prices = sorted(
        [(book, data['price']) for book, data in book_odds.items() if data.get('price', 0) != 0],
        key=lambda x: x[1],
        reverse=True
    )

    retail_prices = [(b, p) for b, p in sorted_prices if b not in SHARP_BOOKS]
    if not retail_prices:
        retail_prices = sorted_prices
    if not retail_prices:
        return _empty_result(market)

    best_book, best_odds = retail_prices[0]

    # Calculate fair probability
    fair_prob, calc_type = calculate_fair_probability(book_odds, opposite_odds, market_key)

    if calc_type == 'none' or fair_prob <= 0:
        return _empty_result(market)

    fair_odds = probability_to_american(fair_prob)

    # EV
    ev_pct = calculate_ev_percentage(fair_prob, best_odds)

    # Kelly
    if best_odds > 0:
        decimal_odds = (best_odds / 100) + 1
    else:
        decimal_odds = (100 / abs(best_odds)) + 1

    if ev_pct > 0:
        std_kelly = calculate_kelly(ev_pct / 100, decimal_odds, fraction=0.25)
    else:
        std_kelly = 0.0

    coverage = len(book_odds)
    conf_multiplier = get_confidence_multiplier(coverage)
    kelly_fraction = std_kelly * conf_multiplier

    return {
        'player': market.get('player', ''),
        'market_key': market_key,
        'line': market.get('line'),
        'side': market.get('side', ''),
        'fair_probability': round(fair_prob, 4),
        'fair_odds': fair_odds,
        'calc_type': calc_type,
        'best_book': best_book,
        'best_odds': best_odds,
        'edge_pct': round(ev_pct, 2),
        'kelly_fraction': round(kelly_fraction, 4),
        'coverage': coverage,
        'confidence_multiplier': round(conf_multiplier, 2),
    }


def _empty_result(market: dict) -> dict:
    return {
        'player': market.get('player', ''),
        'market_key': market.get('market_key', ''),
        'line': market.get('line'),
        'side': market.get('side', ''),
        'fair_probability': 0.0,
        'fair_odds': 0,
        'calc_type': 'none',
        'best_book': '',
        'best_odds': 0,
        'edge_pct': 0.0,
        'kelly_fraction': 0.0,
        'coverage': 0,
        'confidence_multiplier': 0.0,
    }
