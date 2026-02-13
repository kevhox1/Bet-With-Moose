# Bolt Odds Provider Experiment

Real-time odds streaming via [Bolt Odds](https://spro.agency/) WebSocket API.

## Status: Active Testing

- [x] WebSocket connection working
- [x] NBA odds streaming
- [x] Scanner with de-vig methodology
- [x] Test bot for Telegram
- [x] Deep links included
- [ ] Production comparison complete
- [ ] Cost analysis finalized

---

## Key Advantage: Real-Time Streaming

Unlike REST APIs that poll every 30-60 seconds, Bolt Odds uses WebSocket for **instant** updates:

```
REST Polling:     [poll]----60s----[poll]----60s----[poll]
WebSocket:        [connect]→→→→→→→→→[instant updates]→→→→→→
```

**Latency comparison:**
- TheOddsAPI: ~60 seconds
- Bolt Odds: ~0.2 seconds

---

## Files

| File | Purpose |
|------|---------|
| `scanner.py` | Main scanner using WebSocket |
| `bot.py` | Test Telegram bot |
| `tests/` | Connection and latency tests |

---

## API Configuration

```python
# Already configured in scanner.py
BOLT_ODDS_API_KEY = "24ad4285-3c06-4a2a-bc86-77d67ab1cec0"
BOLT_ODDS_WS_URL = f"wss://spro.agency/api?key={API_KEY}"
```

---

## Running

### Test WebSocket Connection
```bash
cd experiments/bolt_odds/tests
python test_websocket.py --duration 30 --sport NBA
```

### Run Test Bot
```bash
cd experiments/bolt_odds
python bot.py
```

---

## Sportsbooks Supported

| Abbrev | Name | Notes |
|--------|------|-------|
| DK | DraftKings | Full coverage |
| FD | FanDuel | Full coverage |
| MG | BetMGM | Full coverage |
| ES | ESPN Bet | Full coverage |
| PN | Pinnacle | Sharp lines |
| BR | BetRivers | Full coverage |
| RK | Hard Rock | Full coverage |
| BB | Bally Bet | Limited |
| BV | Bovada | Offshore |
| BO | BetOnline | Offshore |

---

## WebSocket Message Types

```python
# Initial connection
{"action": "socket_connected"}

# Subscribe to NBA
{"action": "subscribe", "sports": ["NBA"]}

# Initial state (all current odds)
{"action": "initial_state", "data": {...}}

# Real-time update
{"action": "line_update", "data": {...}}

# Game removed
{"action": "game_removed", "data": {...}}
```

---

## How It Works

1. **Connect** to WebSocket endpoint
2. **Subscribe** to NBA sport
3. **Receive** initial state with all current odds
4. **Store** in `BoltOddsStore` (thread-safe in-memory cache)
5. **Receive** real-time `line_update` messages as odds change
6. **Scan** on demand using cached data (instant, no API calls)

---

## Cost Comparison

| Provider | Price | Update Speed | Deep Links |
|----------|-------|--------------|------------|
| TheOddsAPI 60s | ~$119/mo | 60 seconds | No |
| TheOddsAPI 5s | ~$249/mo | 5 seconds | No |
| Bolt Odds | $219/mo | Real-time | Yes |

---

## Test Files

| Test | Purpose |
|------|---------|
| `test_websocket.py` | Connection and latency testing |
| `test_nba_stream.py` | NBA-specific streaming test |
| `test_subscription.py` | Subscription filter testing |
| `test_rest_endpoints.py` | REST fallback testing |
| `cost_comparison.py` | API cost analysis |

---

## Deployment (VPS)

See `tests/README.md` for full deployment guide, or use:

```bash
# On VPS
cd /root/NBA-Long-Shot-Scanner-Bot/experiments/bolt_odds
python bot.py
```

For systemd service, create `/etc/systemd/system/nba-bolt-test.service`.
