#!/usr/bin/env python3
"""Debug script to check OddsBlaze API response and scanning pipeline."""

import requests
import json
import sys
from collections import defaultdict

# Add parent directory to import from oddsblaze_bot
sys.path.insert(0, '.')
from oddsblaze_bot import (
    fetch_all_odds, aggregate_player_props, scan_for_value,
    calculate_fair_probability, build_opposite_lookup, market_to_key,
    SPORTSBOOKS
)

API_KEY = "817d4e80-1e7f-488b-90ed-0c7ef1e435ba"
API_BASE_URL = "https://odds.oddsblaze.com/"

def test_full_pipeline():
    """Test the full scanning pipeline."""
    print("\n" + "=" * 60)
    print("FULL PIPELINE TEST")
    print("=" * 60)

    # Step 1: Fetch odds
    print("\n1. Fetching odds from all sportsbooks...")
    all_odds = fetch_all_odds()
    print(f"   Books with data: {list(all_odds.keys())}")

    # Step 2: Aggregate props
    print("\n2. Aggregating player props...")
    props = aggregate_player_props(all_odds)
    print(f"   Total unique props: {len(props)}")

    if props:
        # Show sample props
        print("\n   Sample props (first 5):")
        for i, (key, data) in enumerate(list(props.items())[:5]):
            books = list(data['books'].keys())
            prices = [data['books'][b]['price'] for b in books]
            print(f"   - {key}")
            print(f"     Books: {books}, Prices: {prices}")

    # Step 3: Scan for value
    print("\n3. Scanning for value (min_ev=0, min_odds=0)...")
    opportunities = scan_for_value(props, min_ev=0, min_odds=0)
    print(f"   Opportunities found: {len(opportunities)}")

    if opportunities:
        print("\n   Top 5 opportunities:")
        for opp in opportunities[:5]:
            print(f"   - {opp['player']} {opp['market']}")
            print(f"     Best: {opp['best_book']} @ {opp['best_odds']}")
            print(f"     EV: {opp['ev_pct']:.1f}%, Kelly: {opp['kelly']:.2f}, Tier: {opp['tier']}")
    else:
        # Debug why no opportunities
        print("\n   DEBUGGING: Why no opportunities?")
        from oddsblaze_bot import (
            calculate_ev_percentage, calculate_kelly, probability_to_american,
            american_to_probability, SHARP_BOOKS
        )

        # Check props with 2+ books
        multi_book_props = {k: v for k, v in props.items() if len(v['books']) >= 2}
        print(f"   Props with 2+ books: {len(multi_book_props)}")

        opposite_lookup = build_opposite_lookup(props)

        # Find props with highest potential EV
        ev_list = []
        for prop_key, prop_data in multi_book_props.items():
            books = prop_data['books']
            market = prop_data['market']
            market_key = market_to_key(market)

            # Get best retail odds
            sorted_prices = sorted(
                [(book, data['price']) for book, data in books.items()],
                key=lambda x: x[1],
                reverse=True
            )
            retail_prices = [(b, p) for b, p in sorted_prices if b not in SHARP_BOOKS]
            if not retail_prices:
                retail_prices = sorted_prices
            best_book, best_odds = retail_prices[0]

            # Calculate fair prob
            opp_odds = opposite_lookup.get(prop_key)
            fair_prob, calc_type = calculate_fair_probability(books, opp_odds, market_key)

            if fair_prob > 0 and calc_type != 'none':
                ev_pct = calculate_ev_percentage(fair_prob, best_odds)
                ev_list.append({
                    'key': prop_key,
                    'best_book': best_book,
                    'best_odds': best_odds,
                    'fair_prob': fair_prob,
                    'ev_pct': ev_pct,
                    'calc_type': calc_type,
                    'coverage': len(books),
                })

        # Sort by EV
        ev_list.sort(key=lambda x: x['ev_pct'], reverse=True)

        print(f"\n   Props with calculated EV: {len(ev_list)}")
        print(f"   Props with EV > 0: {len([x for x in ev_list if x['ev_pct'] > 0])}")
        print(f"   Props with EV > 5%: {len([x for x in ev_list if x['ev_pct'] > 5])}")

        if ev_list:
            print("\n   TOP 10 BY EV (even if negative):")
            for item in ev_list[:10]:
                fair_odds = probability_to_american(item['fair_prob'])
                print(f"   - {item['key'][:50]}...")
                print(f"     Best: {item['best_book']} @ {item['best_odds']:+d}, Fair: {fair_odds:+d}")
                print(f"     EV: {item['ev_pct']:.1f}%, Fair prob: {item['fair_prob']:.3f}, Type: {item['calc_type']}")
                print()

def main():
    print("=" * 60)
    print("OddsBlaze API Debug")
    print("=" * 60)

    total_events = 0
    total_odds = 0
    player_props = 0

    for book in SPORTSBOOKS:
        try:
            url = f"{API_BASE_URL}?key={API_KEY}&sportsbook={book}&league=nba"
            response = requests.get(url, timeout=30)

            if response.status_code == 200:
                data = response.json()
                events = data.get('events', [])
                print(f"\n{book.upper()}: {len(events)} events")

                total_events += len(events)

                for event in events:
                    odds = event.get('odds', [])
                    total_odds += len(odds)

                    # Count player props
                    for odd in odds:
                        market = odd.get('market', '')
                        if 'Player' in market or 'First Basket' in market:
                            player_props += 1

                    # Show first event details
                    if events and book == 'draftkings':
                        teams = event.get('teams', {})
                        away = teams.get('away', {}).get('name', '?')
                        home = teams.get('home', {}).get('name', '?')
                        print(f"  Sample event: {away} @ {home}")
                        print(f"  Odds count: {len(odds)}")

                        # Show first few player prop markets
                        prop_markets = set()
                        for odd in odds[:50]:
                            market = odd.get('market', '')
                            if 'Player' in market or 'First Basket' in market:
                                prop_markets.add(market)

                        if prop_markets:
                            print(f"  Player prop markets: {list(prop_markets)[:5]}")
            else:
                print(f"\n{book.upper()}: HTTP {response.status_code}")
                print(f"  Response: {response.text[:200]}")

        except Exception as e:
            print(f"\n{book.upper()}: ERROR - {e}")

    print("\n" + "=" * 60)
    print(f"TOTALS:")
    print(f"  Total events: {total_events}")
    print(f"  Total odds entries: {total_odds}")
    print(f"  Player prop entries: {player_props}")
    print("=" * 60)

if __name__ == "__main__":
    main()
    test_full_pipeline()
