# Bolt Odds API Testing

Testing scripts for evaluating the Bolt Odds API as a potential alternative/supplement to TheOddsAPI.

## API Overview

- **Provider:** Bolt Odds (https://boltodds.com)
- **Documentation:** https://boltodds.com/docs
- **Primary Interface:** WebSocket (real-time streaming)
- **Rate Limit:** 12 requests/minute per IP

## Key Differences from TheOddsAPI

| Feature | TheOddsAPI | Bolt Odds |
|---------|------------|-----------|
| Data Delivery | REST polling | WebSocket streaming |
| Latency | Request-response cycle (~500ms) | Real-time push (<50ms updates) |
| Pricing Model | Per-request credits | Subscription-based |
| Deep Links | No | **Yes** (direct to sportsbooks!) |
| Pinnacle | Yes | **Yes** (critical for de-vig) |

## Test Scripts

### 1. REST Endpoint Tester (`test_rest_endpoints.py`)
Tests the REST endpoints to discover available sports, sportsbooks, and markets.

### 2. WebSocket Tester (`test_websocket.py`)
Tests real-time WebSocket connection for latency and message format analysis.

### 3. NBA Stream Test (`test_nba_stream.py`)
Connects and subscribes to NBA data, analyzes structure.

### 4. NBA Odds Fetcher (`fetch_nba_odds.py`)
Fetches full NBA odds and shows all available markets by sportsbook.

## Requirements

```bash
pip install requests websockets
```

## API Key (Trial)

```python
API_KEY = "24ad4285-3c06-4a2a-bc86-77d67ab1cec0"
```

---

## Test Results (January 22, 2026)

### Connection Performance

| Metric | Value |
|--------|-------|
| WebSocket connect time | ~250-380ms |
| Time to first message | ~30ms |
| REST endpoint latency | 120-550ms |

### Available Sportsbooks (35 total, 16+ with NBA)

**With NBA Player Props:**
| Sportsbook | Markets | Longshot Props |
|------------|---------|----------------|
| pokerstars | 51 | Double-Doubles, Triple-Doubles, First Basket, First Team Basket, all player stats |
| thescore | 23 | Double-Doubles, Triple-Doubles, First Basket |
| espnbet | 23 | Double-Doubles, Triple-Doubles, First Basket |
| playnow | 43 | Double-Doubles, First Basket |
| sportsinteraction | 39 | Double-Doubles, First Field Goal |
| betmgm | 39 | First Field Goal |
| fanduel | 37 | Points, Rebounds, Assists, Threes, combos |
| bwin | 27 | Points, Rebounds, Assists, Blocks, combos |
| hardrock | 37 | Full player props |
| **pinnacle** | 12 | Game lines only (essential for de-vig!) |

### Available NBA Markets

**Longshot Props (our focus):**
- First Basket / First Team Basket
- First Field Goal
- Double-Doubles
- Triple-Doubles

**Standard Player Props:**
- Points, Rebounds, Assists, Threes, Blocks, Steals
- Points + Rebounds, Points + Assists, Points + Rebounds + Assists
- Assists + Rebounds, Steals + Blocks

**Game Lines:**
- Moneyline, Spread, Total, Team Total
- Quarter/Half lines (1Q, 2Q, 3Q, 4Q, 1H, 2H)

### Data Structure

```json
{
  "Kevin Durant First Basket": {
    "odds": "+500",
    "link": "https://thescore.bet/sport/basketball/...",
    "outcome_name": "First Basket",
    "outcome_line": null,
    "outcome_over_under": null,
    "outcome_target": "Kevin Durant"
  }
}
```

**Key fields:**
- `odds` - American odds format ("+500", "-110")
- `link` - **Direct deep link to sportsbook bet slip!**
- `outcome_name` - Market type
- `outcome_target` - Player or team name
- `outcome_line` - Line value (e.g., "25.5" for over/under)
- `outcome_over_under` - "Over", "Under", or null

### WebSocket Subscription Format

```python
# Subscribe to NBA odds
await ws.send(json.dumps({"action": "subscribe", "sports": ["NBA"]}))
```

### Games Per Night

8 NBA games tested (Jan 22, 2026):
- Philadelphia 76ers vs Houston Rockets
- Orlando Magic vs Charlotte Hornets
- Washington Wizards vs Denver Nuggets
- Dallas Mavericks vs Golden State Warriors
- Minnesota Timberwolves vs Chicago Bulls
- Utah Jazz vs San Antonio Spurs
- Portland Trail Blazers vs Miami Heat
- Los Angeles Clippers vs Los Angeles Lakers

**Outcomes per game:** 600-900 individual betting lines

---

## Comparison Summary

### Pros of Bolt Odds
1. **Deep links included** - Can link directly to bet slip
2. **Real-time streaming** - Lower latency than polling
3. **Pinnacle available** - Critical for de-vigging
4. **Rich player props** - Double-doubles, Triple-doubles, First Basket all available
5. **Many sportsbooks** - 16+ books with NBA data

### Cons / Considerations
1. **WebSocket complexity** - More complex than REST
2. **Subscription model** - Different cost structure than pay-per-call
3. **Trial limitations** - Some features may be limited

### Recommendation

Bolt Odds could be a strong addition/alternative to TheOddsAPI for the scanner bot:
- Has all the longshot markets we need
- Includes Pinnacle for accurate de-vigging
- Deep links would eliminate manual bet placement
- Real-time updates could enable faster alerts

---

## Pricing Comparison (January 2026)

### Bolt Odds Plans (Flat Monthly Rate)

| Plan | Monthly | Sports | Markets | Notes |
|------|---------|--------|---------|-------|
| Starter | $99 | 1 | 1 market | Too limited |
| **Growth** | **$219** | 3 | All | **Recommended for NBA** |
| Pro | $349 | All | All | Multi-sport expansion |

### TheOddsAPI (Per-Request)

| Polling Interval | Requests/Month | Monthly Cost |
|------------------|----------------|--------------|
| 1s (real-time) | 6,480,000 | ~$96,274 |
| 5s | 1,296,000 | ~$18,514 |
| 10s | 648,000 | ~$8,794 |
| 30s | 216,000 | ~$2,314 |
| 60s (current) | 108,000 | ~$694 |
| 5m | 21,600 | ~$79 |

### Break-Even Analysis

- **Break-even point: ~85 seconds**
- Faster than 85s → Bolt Odds is cheaper
- Slower than 85s → TheOddsAPI is cheaper
- At real-time (0.2s) → Bolt Odds is **440x cheaper**

### Cost Script

Run `python cost_comparison.py` for detailed analysis.
