#!/usr/bin/env python3
"""
Bolt Odds REST API Endpoint Tester

Tests the REST endpoints to discover:
- Available sports
- Available sportsbooks
- Available markets
- Available games

Usage: python test_rest_endpoints.py
"""

import requests
import json
import time
from datetime import datetime

# Bolt Odds API configuration
API_KEY = "24ad4285-3c06-4a2a-bc86-77d67ab1cec0"
BASE_URL = "https://spro.agency/api"

def make_request(endpoint: str, params: dict = None) -> dict:
    """Make a GET request to the Bolt Odds API."""
    url = f"{BASE_URL}/{endpoint}"
    if params is None:
        params = {}
    params['key'] = API_KEY

    start_time = time.time()
    try:
        response = requests.get(url, params=params, timeout=30)
        latency_ms = (time.time() - start_time) * 1000

        print(f"\n{'='*60}")
        print(f"Endpoint: {endpoint}")
        print(f"URL: {response.url}")
        print(f"Status: {response.status_code}")
        print(f"Latency: {latency_ms:.2f}ms")
        print(f"{'='*60}")

        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error response: {response.text}")
            return None
    except Exception as e:
        print(f"Request failed: {e}")
        return None


def test_get_info():
    """Test the get_info endpoint to see available sports and sportsbooks."""
    print("\n" + "="*80)
    print("TESTING: /api/get_info - Available Sports & Sportsbooks")
    print("="*80)

    data = make_request("get_info")
    if data:
        # Pretty print the response
        print("\nResponse structure:")
        print(json.dumps(data, indent=2, default=str)[:3000])  # Limit output

        # Extract key info
        if isinstance(data, dict):
            if 'sports' in data:
                print(f"\n📊 Available Sports ({len(data['sports'])}):")
                for sport in data['sports']:
                    print(f"  - {sport}")
            if 'sportsbooks' in data:
                print(f"\n📚 Available Sportsbooks ({len(data['sportsbooks'])}):")
                for book in data['sportsbooks']:
                    print(f"  - {book}")
        return data
    return None


def test_get_games(sport: str = None):
    """Test the get_games endpoint to see available games."""
    print("\n" + "="*80)
    print(f"TESTING: /api/get_games - Available Games" + (f" (sport={sport})" if sport else ""))
    print("="*80)

    params = {}
    if sport:
        params['sports'] = sport

    data = make_request("get_games", params)
    if data:
        print("\nResponse structure (first 3000 chars):")
        print(json.dumps(data, indent=2, default=str)[:3000])

        # Count games by sport if possible
        if isinstance(data, list):
            print(f"\n🎮 Total games returned: {len(data)}")
            # Try to categorize by sport
            sports_count = {}
            for game in data:
                if isinstance(game, dict):
                    sport_name = game.get('sport', 'unknown')
                    sports_count[sport_name] = sports_count.get(sport_name, 0) + 1
            if sports_count:
                print("Games by sport:")
                for s, c in sorted(sports_count.items()):
                    print(f"  - {s}: {c}")
        return data
    return None


def test_get_markets(sport: str = None, sportsbook: str = None):
    """Test the get_markets endpoint to see available market types."""
    print("\n" + "="*80)
    print(f"TESTING: /api/get_markets - Available Markets")
    if sport or sportsbook:
        print(f"Filters: sport={sport}, sportsbook={sportsbook}")
    print("="*80)

    params = {}
    if sport:
        params['sports'] = sport
    if sportsbook:
        params['sportsbooks'] = sportsbook

    data = make_request("get_markets", params)
    if data:
        print("\nResponse structure (first 5000 chars):")
        print(json.dumps(data, indent=2, default=str)[:5000])

        # Try to extract market names
        if isinstance(data, list):
            print(f"\n📈 Total markets returned: {len(data)}")
            # Show unique market names
            market_names = set()
            for item in data:
                if isinstance(item, dict):
                    name = item.get('market', item.get('name', item.get('outcome_name', str(item))))
                    market_names.add(name)
                elif isinstance(item, str):
                    market_names.add(item)
            if market_names:
                print(f"\nUnique market types ({len(market_names)}):")
                for m in sorted(market_names):
                    print(f"  - {m}")
        elif isinstance(data, dict):
            print(f"\nMarket categories: {list(data.keys())}")
        return data
    return None


def test_get_parlays(sportsbook: str = "DraftKings"):
    """Test the get_parlays endpoint."""
    print("\n" + "="*80)
    print(f"TESTING: /api/get_parlays - Parlay Data (sportsbook={sportsbook})")
    print("="*80)

    data = make_request("get_parlays", {'sportsbooks': sportsbook})
    if data:
        print("\nResponse structure (first 3000 chars):")
        print(json.dumps(data, indent=2, default=str)[:3000])
        return data
    return None


def main():
    """Run all REST endpoint tests."""
    print("\n" + "#"*80)
    print("#" + " "*30 + "BOLT ODDS API TESTER" + " "*28 + "#")
    print("#" + " "*25 + f"Run at: {datetime.now().isoformat()}" + " "*17 + "#")
    print("#"*80)

    results = {}

    # Test 1: Get available sports and sportsbooks
    results['info'] = test_get_info()
    time.sleep(1)  # Respect rate limits

    # Test 2: Get all available games
    results['games'] = test_get_games()
    time.sleep(1)

    # Test 3: Get NBA-specific games (if NBA is available)
    results['nba_games'] = test_get_games(sport="NBA")
    time.sleep(1)

    # Test 4: Get all markets
    results['markets'] = test_get_markets()
    time.sleep(1)

    # Test 5: Get NBA-specific markets
    results['nba_markets'] = test_get_markets(sport="NBA")
    time.sleep(1)

    # Test 6: Get DraftKings markets
    results['dk_markets'] = test_get_markets(sportsbook="DraftKings")
    time.sleep(1)

    # Test 7: Get parlays
    results['parlays'] = test_get_parlays()

    # Summary
    print("\n" + "#"*80)
    print("#" + " "*30 + "TEST SUMMARY" + " "*36 + "#")
    print("#"*80)

    for test_name, data in results.items():
        status = "✅ Success" if data else "❌ Failed/Empty"
        print(f"  {test_name}: {status}")

    print("\n" + "#"*80)
    print("Done!")


if __name__ == "__main__":
    main()
