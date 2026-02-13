"""Tests for Kelly and EV calculations."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.kelly import calculate_ev_percentage, calculate_kelly


def test_ev_positive_odds():
    # fair_prob=0.5, best_odds=+110 → decimal=2.1 → EV=(0.5*2.1-1)*100=5%
    ev = calculate_ev_percentage(0.5, 110)
    assert abs(ev - 5.0) < 0.01


def test_ev_negative_odds():
    # fair_prob=0.6, best_odds=-150 → decimal=1.6667 → EV=(0.6*1.6667-1)*100=0%
    ev = calculate_ev_percentage(0.6, -150)
    assert abs(ev - 0.0) < 0.1


def test_ev_zero():
    assert calculate_ev_percentage(0.0, 100) == 0.0
    assert calculate_ev_percentage(0.5, 0) == 0.0


def test_kelly_basic():
    # edge=0.05, decimal=3.0 → full kelly=0.05/2=0.025, quarter=0.00625, *100=0.625 units
    result = calculate_kelly(0.05, 3.0, fraction=0.25)
    assert abs(result - 0.625) < 0.001


def test_kelly_zero_edge():
    assert calculate_kelly(0.0, 3.0) == 0.0
    assert calculate_kelly(-0.05, 3.0) == 0.0


def test_kelly_bad_odds():
    assert calculate_kelly(0.05, 1.0) == 0.0
    assert calculate_kelly(0.05, 0.5) == 0.0
