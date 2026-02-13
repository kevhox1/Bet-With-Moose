#!/usr/bin/env python3
"""
Cost Comparison: Bolt Odds vs TheOddsAPI

Compares costs at various polling intervals for NBA longshot scanner.
"""

# =============================================================================
# BOLT ODDS PRICING (Subscription - Flat Monthly)
# =============================================================================

BOLT_ODDS_PLANS = {
    "Starter": {
        "monthly": 99,
        "yearly": 948,
        "sports": 1,
        "markets": "1 market type",
        "connections": 1,
        "notes": "Too limited - only 1 market"
    },
    "Growth": {
        "monthly": 219,
        "yearly": 2148,
        "sports": 3,
        "markets": "All markets",
        "connections": 1,
        "notes": "Would work - NBA + all markets"
    },
    "Pro": {
        "monthly": 349,
        "yearly": 3348,
        "sports": "All",
        "markets": "All markets",
        "connections": 3,
        "notes": "Best for expansion (NHL, MLB, etc)"
    }
}

# =============================================================================
# THEODDSAPI PRICING (Per-Request)
# =============================================================================

# TheOddsAPI costs (approximate based on their pricing page)
# Free tier: 500 requests/month
# Starter: $19/month for 5,000 requests
# Pro: $79/month for 25,000 requests
# Business: $199/month for 75,000 requests
# Enterprise: Custom

THEODDSAPI_PLANS = {
    "Free": {"monthly": 0, "requests": 500},
    "Starter": {"monthly": 19, "requests": 5000},
    "Pro": {"monthly": 79, "requests": 25000},
    "Business": {"monthly": 199, "requests": 75000},
}

# Cost per request at overage (approximately $0.01-0.02 per request)
OVERAGE_COST_PER_REQUEST = 0.015

# =============================================================================
# SCANNER CONFIGURATION
# =============================================================================

# Markets we scan (from nba_value_scanner.py)
MARKETS = [
    "player_double_double",
    "player_triple_double",
    "player_first_basket",
    "player_first_team_basket",
    "player_points_alternate",
    "player_rebounds_alternate",
    "player_assists_alternate",
    "player_blocks_alternate",
    "player_steals_alternate",
    "player_threes_alternate",
]

# Scanning assumptions
GAMES_PER_NIGHT = 8  # Average NBA games per night
ACTIVE_HOURS_PER_DAY = 6  # Hours when games are live (roughly 7pm-1am)
DAYS_PER_MONTH = 30
NBA_SEASON_MONTHS = 7  # October through April

# TheOddsAPI: Each market request = 1 request per game
# So 10 markets × 8 games = 80 requests per scan cycle

def calculate_theoddsapi_requests(interval_seconds: int) -> dict:
    """Calculate TheOddsAPI requests at a given polling interval."""
    scans_per_hour = 3600 / interval_seconds
    scans_per_day = scans_per_hour * ACTIVE_HOURS_PER_DAY
    scans_per_month = scans_per_day * DAYS_PER_MONTH

    # Each scan = requests for all markets across all games
    # TheOddsAPI batches by market, so roughly 10 API calls per scan
    requests_per_scan = len(MARKETS)  # 10 markets = 10 requests

    total_requests = scans_per_month * requests_per_scan

    return {
        "interval_seconds": interval_seconds,
        "scans_per_hour": scans_per_hour,
        "scans_per_day": scans_per_day,
        "scans_per_month": int(scans_per_month),
        "requests_per_month": int(total_requests),
    }


def calculate_theoddsapi_cost(requests: int) -> dict:
    """Calculate TheOddsAPI cost for a given number of requests."""
    for plan_name, plan in sorted(THEODDSAPI_PLANS.items(), key=lambda x: x[1]["requests"]):
        if requests <= plan["requests"]:
            return {
                "plan": plan_name,
                "base_cost": plan["monthly"],
                "overage": 0,
                "total_cost": plan["monthly"],
            }

    # Need Business plan + overage
    base = THEODDSAPI_PLANS["Business"]
    overage_requests = requests - base["requests"]
    overage_cost = overage_requests * OVERAGE_COST_PER_REQUEST

    return {
        "plan": "Business + Overage",
        "base_cost": base["monthly"],
        "overage": overage_cost,
        "total_cost": base["monthly"] + overage_cost,
    }


def main():
    print("=" * 90)
    print("COST COMPARISON: BOLT ODDS vs THEODDSAPI")
    print("=" * 90)
    print(f"\nScanner Configuration:")
    print(f"  Markets: {len(MARKETS)} longshot markets")
    print(f"  Games/night: ~{GAMES_PER_NIGHT}")
    print(f"  Active hours/day: {ACTIVE_HOURS_PER_DAY}")
    print(f"  Days/month: {DAYS_PER_MONTH}")

    # ==========================================================================
    # BOLT ODDS COST (Flat rate - doesn't depend on polling interval!)
    # ==========================================================================
    print("\n" + "=" * 90)
    print("BOLT ODDS (WebSocket Streaming - Flat Monthly Rate)")
    print("=" * 90)
    print("\n** Key insight: Bolt Odds is FLAT RATE - polling interval doesn't affect cost! **")
    print("** You get real-time streaming (~0.2 second updates) for the same price **\n")

    print(f"{'Plan':<12} {'Monthly':>10} {'Yearly':>10} {'Sports':<10} {'Markets':<15} {'Notes'}")
    print("-" * 90)
    for plan_name, plan in BOLT_ODDS_PLANS.items():
        print(f"{plan_name:<12} ${plan['monthly']:>8}/mo ${plan['yearly']:>7}/yr {str(plan['sports']):<10} {plan['markets']:<15} {plan['notes']}")

    print("\n➡️  Recommended for NBA scanner: Growth plan ($219/month)")
    print("   - Includes all markets (alternates, first basket, double/triple doubles)")
    print("   - Real-time streaming (0.2s latency vs 60s)")
    print("   - Deep links included")

    # ==========================================================================
    # THEODDSAPI COST (Per-request - depends on polling interval)
    # ==========================================================================
    print("\n" + "=" * 90)
    print("THEODDSAPI (REST Polling - Per-Request Pricing)")
    print("=" * 90)

    intervals = [1, 5, 10, 20, 30, 60, 120, 300]  # seconds

    print(f"\n{'Interval':<12} {'Scans/hr':>10} {'Req/month':>12} {'Plan':<20} {'Cost/month':>12}")
    print("-" * 90)

    for interval in intervals:
        usage = calculate_theoddsapi_requests(interval)
        cost = calculate_theoddsapi_cost(usage["requests_per_month"])

        interval_str = f"{interval}s" if interval < 60 else f"{interval//60}m"
        print(f"{interval_str:<12} {usage['scans_per_hour']:>10.0f} {usage['requests_per_month']:>12,} {cost['plan']:<20} ${cost['total_cost']:>10,.2f}")

    # ==========================================================================
    # COMPARISON TABLE
    # ==========================================================================
    print("\n" + "=" * 90)
    print("SIDE-BY-SIDE COMPARISON")
    print("=" * 90)

    bolt_growth = 219  # Monthly cost for Growth plan

    print(f"\n{'Polling Interval':<18} {'TheOddsAPI':>15} {'Bolt Odds':>15} {'Savings':>15} {'Notes'}")
    print("-" * 90)

    comparisons = [
        (1, "Real-time equivalent"),
        (5, "Very fast"),
        (10, "Fast"),
        (20, "Moderate"),
        (30, "Standard"),
        (60, "Current (TheOddsAPI default)"),
    ]

    for interval, note in comparisons:
        usage = calculate_theoddsapi_requests(interval)
        cost = calculate_theoddsapi_cost(usage["requests_per_month"])
        theodds_cost = cost["total_cost"]

        savings = theodds_cost - bolt_growth
        savings_str = f"+${abs(savings):,.0f}" if savings > 0 else f"-${abs(savings):,.0f}"
        winner = "Bolt Odds" if savings > 0 else "TheOddsAPI"

        interval_str = f"{interval}s" if interval < 60 else f"{interval//60}m"
        print(f"{interval_str:<18} ${theodds_cost:>13,.2f} ${bolt_growth:>13,.2f} {savings_str:>15} {note}")

    # ==========================================================================
    # BREAK-EVEN ANALYSIS
    # ==========================================================================
    print("\n" + "=" * 90)
    print("BREAK-EVEN ANALYSIS")
    print("=" * 90)

    # Find the interval where TheOddsAPI becomes cheaper than Bolt Odds Growth
    for interval in range(1, 600):
        usage = calculate_theoddsapi_requests(interval)
        cost = calculate_theoddsapi_cost(usage["requests_per_month"])
        if cost["total_cost"] <= bolt_growth:
            print(f"\n✂️  Break-even point: ~{interval} seconds")
            print(f"   At {interval}s intervals, TheOddsAPI costs ${cost['total_cost']:.2f}/month")
            print(f"   Bolt Odds Growth costs ${bolt_growth}/month")
            break

    # ==========================================================================
    # RECOMMENDATION
    # ==========================================================================
    print("\n" + "=" * 90)
    print("RECOMMENDATION")
    print("=" * 90)

    print("""
    Current Setup (TheOddsAPI @ 60s):
    - Cost: ~$79-199/month (depending on usage)
    - Latency: 60 seconds
    - No deep links

    Bolt Odds Growth Plan ($219/month):
    - Cost: $219/month (flat)
    - Latency: 0.2 seconds (300x faster!)
    - Deep links included
    - All alternate markets
    - Pinnacle for de-vigging

    💡 If you want latency faster than ~80 seconds, Bolt Odds is more cost-effective.
    💡 The real value is the 300x speed improvement + deep links.
    💡 For a betting scanner, faster = more edge captured before lines move.
    """)


if __name__ == "__main__":
    main()
