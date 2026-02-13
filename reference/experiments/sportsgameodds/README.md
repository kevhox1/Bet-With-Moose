# SportsGameOdds Provider Experiment

Real-time odds provider using [SportsGameOdds.com](https://sportsgameodds.com/) API.

## Status: WebSocket + Telegram Working

- [x] REST API tested (~2.3s latency)
- [x] WebSocket streaming via Pusher - **WORKING**
- [x] Detailed change tracking (player, stat, book, price movement)
- [x] Production markets and de-vig multipliers configured
- [x] **Telegram alerts integrated** - `websocket_bot.py`
- [ ] Fix VPS DNS issues (works locally on Mac)

---

## Quick Start - WebSocket Bot with Telegram (Recommended)

Run locally on Mac to get real-time alerts to Telegram:

```bash
cd experiments/sportsgameodds
pip install -r requirements.txt
python websocket_bot.py
```

This will:
1. Connect to SportsGameOdds WebSocket via Pusher
2. Run the scanner with de-vig methodology on every update
3. Send +EV alerts to Telegram (SGO_Test_Bot channel)

---

## Quick Start - Node.js Only (No Telegram)

```bash
cd experiments/sportsgameodds
npm install
node pusher_stream.js
```

This will:
1. Connect to SportsGameOdds WebSocket via Pusher
2. Subscribe to NBA pre-game odds channel
3. Show real-time player prop changes as they happen (console only)

---

## Files

| File | Purpose | Status |
|------|---------|--------|
| `websocket_bot.py` | **WebSocket + Scanner + Telegram** - USE THIS | **Active** |
| `pusher_stream.js` | Node.js WebSocket client (console only) | Working |
| `requirements.txt` | Python dependencies for websocket_bot | Active |
| `pusher_stream_v2.js` | Hybrid version for VPS DNS issues | Backup |
| `start_stream.py` | Python launcher for pusher_stream_v2 | Backup |
| `sgo_scanner.py` | Scanner with production markets + de-vig | Ready |
| `test_latency.py` | REST API latency testing | Complete |
| `sockjs_stream.py` | SockJS transport attempt | Experimental |
| `websocket_stream.py` | Raw WebSocket attempt | Experimental |
| `provider.py` | REST/WebSocket API client | Legacy |
| `scanner.py` | Original scanner | Legacy |
| `sgo_bot.py` | Telegram bot skeleton | Skeleton |

---

## API Credentials

```
API Key: 7546525eada0352b926e60dbc6c42cb0
API Base: https://api.sportsgameodds.com/v2
Pusher Key: b633e6e9d4f43de68d89
Pusher Cluster: us2
Channel: presence-events-upcoming-NBA
```

---

## Player Prop Markets

Tracking these stats (matching production):

| Stat ID | Market |
|---------|--------|
| `points` | Player Points |
| `rebounds` | Player Rebounds |
| `assists` | Player Assists |
| `threePointersMade` | Player 3-Pointers |
| `blocks` | Player Blocks |
| `steals` | Player Steals |
| `doubleDouble` | Double-Double |
| `tripleDouble` | Triple-Double |
| `firstBasket` | First Basket |
| `points+rebounds` | Points + Rebounds |
| `points+assists` | Points + Assists |
| `points+rebounds+assists` | PRA Combo |

**Note:** `player_first_team_basket` is not available in SportsGameOdds.

---

## De-Vig Multipliers

From production MKB V10 methodology (in `sgo_scanner.py`):

```python
MARKET_MULTIPLIERS = {
    "player_points_alternate": 1.0,
    "player_rebounds_alternate": 1.0,
    "player_assists_alternate": 1.0,
    "player_threes_alternate": 1.0,
    "player_blocks_alternate": 1.05,
    "player_steals_alternate": 1.05,
    "player_double_double": 1.05,
    "player_triple_double": 1.1,
    "player_first_basket": 1.2,
}
```

---

## WebSocket Behavior

- Updates arrive in batches (~every 30 seconds)
- Each update contains list of changed eventIDs
- Must call REST API to get full odds data
- First update cycle shows "(NEW)" for all odds (cache warming)
- Subsequent updates show actual price movements

Example output:
```
[UPDATE #2] 1 event(s) changed @ 05:02:15
   Fetched in 225ms

   Bucks @ 76ers
   Tyrese Maxey points over 24.5: fanduel +100 -> +105
   Joel Embiid rebounds under 11.5: draftkings -110 -> -115
   ... and 45 more changes
```

---

## Known Issues

### VPS DNS Resolution
Node.js on the VPS has DNS issues with `api.sportsgameodds.com` and `ws-us2.pusher.com`:
```
Error: getaddrinfo EAI_AGAIN api.sportsgameodds.com
```

**Workarounds:**
1. Run locally on Mac (works perfectly)
2. Use `pusher_stream_v2.js` + `start_stream.py` (Python handles DNS better)

### Pusher WebSocket Disabled
The Pusher app has `websocket: false` in its config, forcing SockJS transport. The official `pusher-js` library handles this automatically.

---

## Next Steps

1. ~~**Integrate scanning logic**~~ - DONE via `websocket_bot.py`
2. ~~**Connect to Telegram**~~ - DONE via `websocket_bot.py`
3. **Fix VPS DNS** - Either fix VPS DNS or deploy via different method
4. **Compare with production** - Run side-by-side with TheOddsAPI scanner

---

## API Documentation

- [SportsGameOdds Docs](https://sportsgameodds.com/docs/)
- [WebSocket Streaming](https://sportsgameodds.com/docs/real-time-streaming)
- [API Reference](https://sportsgameodds.com/docs/reference)

---

## Test Telegram Channel

```
Channel: SGO_Test_Bot
Chat ID: -1003336875829
Bot Token: 8433115695:AAHIY27eEnfKMaL-SsVQL5dXUKuewpSpm18
```
