"""
Quick test script for SportsGameOdds API
Run: python test_api.py
"""

import requests
import json

API_KEY = "7546525eada0352b926e60dbc6c42cb0"
BASE_URL = "https://api.sportsgameodds.com/v2"

def test_api():
    """Test basic API connectivity and explore endpoints."""

    headers = {
        'x-api-key': API_KEY,  # Try different auth methods
        'Content-Type': 'application/json',
    }

    # Also try as query param
    params = {
        'apiKey': API_KEY,
    }

    print("=" * 60)
    print("Testing SportsGameOdds API")
    print("=" * 60)

    # Test 1: Try different auth methods
    print("\n1. Testing authentication methods...")

    # Method A: x-api-key header
    print("   Trying x-api-key header...")
    r = requests.get(f"{BASE_URL}/events", headers=headers, timeout=30)
    print(f"   Status: {r.status_code}")
    if r.status_code == 200:
        print("   ✓ x-api-key header works!")
        data = r.json()
        print(f"   Response keys: {list(data.keys()) if isinstance(data, dict) else 'list'}")
    else:
        print(f"   Response: {r.text[:500]}")

    # Method B: Authorization Bearer header
    print("\n   Trying Authorization Bearer header...")
    headers2 = {'Authorization': f'Bearer {API_KEY}'}
    r = requests.get(f"{BASE_URL}/events", headers=headers2, timeout=30)
    print(f"   Status: {r.status_code}")
    if r.status_code != 200:
        print(f"   Response: {r.text[:500]}")

    # Method C: Query parameter
    print("\n   Trying apiKey query param...")
    r = requests.get(f"{BASE_URL}/events", params=params, timeout=30)
    print(f"   Status: {r.status_code}")
    if r.status_code != 200:
        print(f"   Response: {r.text[:500]}")

    # Test 2: Get NBA events
    print("\n" + "=" * 60)
    print("2. Fetching NBA events...")
    print("=" * 60)

    # Try with leagueID filter
    headers = {'x-api-key': API_KEY}

    # Try different endpoint patterns
    endpoints_to_try = [
        '/events?leagueID=NBA',
        '/events?league=NBA',
        '/events?sport=basketball&league=NBA',
        '/odds?leagueID=NBA',
        '/sports/basketball/events',
        '/leagues/NBA/events',
    ]

    for endpoint in endpoints_to_try:
        print(f"\n   Trying: {BASE_URL}{endpoint}")
        try:
            r = requests.get(f"{BASE_URL}{endpoint}", headers=headers, timeout=30)
            print(f"   Status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict):
                    print(f"   Keys: {list(data.keys())}")
                    if 'data' in data:
                        items = data['data']
                        print(f"   Found {len(items)} items in 'data'")
                        if items:
                            print(f"   First item keys: {list(items[0].keys())}")
                            print(f"   Sample: {json.dumps(items[0], indent=2)[:1000]}")
                elif isinstance(data, list):
                    print(f"   Found {len(data)} items (list)")
                    if data:
                        print(f"   First item keys: {list(data[0].keys())}")
                break
            elif r.status_code == 404:
                print(f"   Not found")
            else:
                print(f"   Error: {r.text[:200]}")
        except Exception as e:
            print(f"   Error: {e}")

    # Test 3: Check available endpoints (if docs endpoint exists)
    print("\n" + "=" * 60)
    print("3. Exploring API structure...")
    print("=" * 60)

    explore_endpoints = [
        '/sports',
        '/leagues',
        '/sportsbooks',
        '/markets',
        '/account',
        '/account/usage',
    ]

    for endpoint in explore_endpoints:
        try:
            r = requests.get(f"{BASE_URL}{endpoint}", headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                print(f"\n   {endpoint}: ✓")
                if isinstance(data, dict):
                    print(f"   Keys: {list(data.keys())}")
                elif isinstance(data, list) and data:
                    print(f"   {len(data)} items, first: {data[0] if len(str(data[0])) < 100 else list(data[0].keys())}")
            else:
                print(f"\n   {endpoint}: {r.status_code}")
        except Exception as e:
            print(f"\n   {endpoint}: Error - {e}")

if __name__ == "__main__":
    test_api()
