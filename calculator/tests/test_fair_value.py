"""Tests for fair value calculation."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.fair_value import calculate_fair_probability


def test_empty_book_odds():
    prob, calc = calculate_fair_probability({})
    assert prob == 0.5
    assert calc == 'none'


def test_two_way_single_book():
    book_odds = {'draftkings': {'price': -110}}
    opp_odds = {'draftkings': {'price': -110}}
    prob, calc = calculate_fair_probability(book_odds, opp_odds)
    assert abs(prob - 0.5) < 0.001
    assert calc == '2-way'


def test_one_way_single_book():
    book_odds = {'draftkings': {'price': -110}}
    prob, calc = calculate_fair_probability(book_odds, None, 'player_points')
    assert calc == '1-way'
    assert 0.0 < prob < 1.0


def test_hybrid_mixed():
    book_odds = {
        'draftkings': {'price': -110},
        'fanduel': {'price': -108},
    }
    opp_odds = {'draftkings': {'price': -110}}  # only DK has opposite
    prob, calc = calculate_fair_probability(book_odds, opp_odds, 'player_points')
    assert calc == 'hybrid'
    assert 0.0 < prob < 1.0


def test_multi_book_weighted():
    """Multiple books should produce weighted average."""
    book_odds = {
        'draftkings': {'price': -110},
        'fanduel': {'price': -105},
        'betmgm': {'price': -115},
    }
    opp_odds = {
        'draftkings': {'price': -110},
        'fanduel': {'price': -115},
        'betmgm': {'price': -105},
    }
    prob, calc = calculate_fair_probability(book_odds, opp_odds, 'player_points')
    assert calc == '2-way'
    assert 0.45 < prob < 0.55


def test_zero_odds_skipped():
    book_odds = {
        'draftkings': {'price': 0},
        'fanduel': {'price': -110},
    }
    prob, calc = calculate_fair_probability(book_odds, None, 'player_points')
    assert calc == '1-way'
    # Should only use fanduel
