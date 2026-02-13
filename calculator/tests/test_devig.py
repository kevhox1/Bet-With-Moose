"""Tests for devig calculations - verified against reference implementation."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.devig import (
    american_to_probability,
    probability_to_american,
    get_one_way_multiplier,
    two_way_devig,
    one_way_devig,
)


def test_american_to_probability_negative():
    # -110 → 110/210 ≈ 0.5238
    assert abs(american_to_probability(-110) - 0.52381) < 0.001


def test_american_to_probability_positive():
    # +200 → 100/300 ≈ 0.3333
    assert abs(american_to_probability(200) - 0.33333) < 0.001


def test_american_to_probability_zero():
    assert american_to_probability(0) == 0.0


def test_probability_to_american_favorite():
    # 0.6 → -150
    assert probability_to_american(0.6) == -150


def test_probability_to_american_underdog():
    # 0.3333 → +200
    result = probability_to_american(1/3)
    assert result == 200


def test_probability_to_american_edge_cases():
    assert probability_to_american(0.0) == 0
    assert probability_to_american(1.0) == 0


def test_get_one_way_multiplier_ranges():
    assert get_one_way_multiplier(-300) == 0.88
    assert get_one_way_multiplier(-150) == 0.90
    assert get_one_way_multiplier(100) == 0.92
    assert get_one_way_multiplier(150) == 0.89
    assert get_one_way_multiplier(300) == 0.86
    assert get_one_way_multiplier(500) == 0.84
    assert get_one_way_multiplier(800) == 0.82
    assert get_one_way_multiplier(1500) == 0.74
    assert get_one_way_multiplier(3000) == 0.72
    assert get_one_way_multiplier(6000) == 0.72


def test_two_way_devig():
    # -110/-110 → each implied ~0.5238, fair = 0.5
    p1 = american_to_probability(-110)
    p2 = american_to_probability(-110)
    assert abs(two_way_devig(p1, p2) - 0.5) < 0.001


def test_two_way_devig_skewed():
    p1 = american_to_probability(-200)  # 0.6667
    p2 = american_to_probability(170)   # 0.3704
    fair = two_way_devig(p1, p2)
    assert 0.63 < fair < 0.65


def test_one_way_devig_longshot():
    # +1500 player_points should use longshot multiplier 0.76
    prob = american_to_probability(1500)  # 0.0625
    fair = one_way_devig(prob, 1500, 'player_points')
    assert abs(fair - prob * 0.76) < 0.0001


def test_one_way_devig_extreme_longshot():
    # +3500 player_threes should use extreme multiplier 0.70
    prob = american_to_probability(3500)
    fair = one_way_devig(prob, 3500, 'player_threes')
    assert abs(fair - prob * 0.70) < 0.0001


def test_one_way_devig_normal_market():
    # -110 player_points: market mult 0.76 vs odds mult 0.92 → use max = 0.92
    prob = american_to_probability(-110)
    fair = one_way_devig(prob, -110, 'player_points')
    assert abs(fair - prob * 0.92) < 0.0001


def test_one_way_devig_no_market_match():
    # Unknown market uses odds multiplier only
    prob = american_to_probability(300)
    fair = one_way_devig(prob, 300, 'unknown_market')
    assert abs(fair - prob * 0.86) < 0.0001
