"""
Sportsbook weighting logic and confidence multipliers.
"""
from config import GLOBAL_WEIGHTS, BOOK_ABBREV_MAP, CONFIDENCE_MULTIPLIERS, DEFAULT_WEIGHT


def get_book_weight(book_name: str) -> float:
    """Get weight for a sportsbook by its full name or abbreviation."""
    book_abbrev = BOOK_ABBREV_MAP.get(book_name.lower(), book_name.upper()[:2])
    return GLOBAL_WEIGHTS.get(book_abbrev, DEFAULT_WEIGHT)


def get_book_abbrev(book_name: str) -> str:
    """Get abbreviation for a sportsbook."""
    return BOOK_ABBREV_MAP.get(book_name.lower(), book_name.upper()[:2])


def get_confidence_multiplier(coverage: int) -> float:
    """Get confidence multiplier based on book coverage."""
    if coverage >= 15:
        return 1.0
    return CONFIDENCE_MULTIPLIERS.get(coverage, 0.50)
