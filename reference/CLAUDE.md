# NBA Long Shot Scanner Bot - Project Context

## Quick Reference

| Environment | Telegram Channel | Odds Provider | Bot Location | Status |
|-------------|------------------|---------------|--------------|--------|
| **Production** | Main Bot (Chat ID: 5892910630) | TheOddsAPI | `src/bot.py` | Active |
| **Test** | SGO_Test_Bot (-1003336875829) | Bolt Odds | `experiments/bolt_odds/bolt_bot.py` | Testing |
| **Test** | SGO_Test_Bot | SportsGameOdds | `experiments/sportsgameodds/sgo_bot.py` | Skeleton |

---

## Repository Structure

```
NBA-Long-Shot-Scanner-Bot/
├── src/                           # PRODUCTION CODE
│   ├── bot.py                     # Main Telegram bot (TheOddsAPI)
│   ├── nba_value_scanner.py       # Production scanner (TheOddsAPI)
│   ├── config.py                  # Environment config
│   ├── database.py                # SQLite for settings/history
│   ├── bet_logger.py              # ROI tracking
│   ├── bet_grader.py              # Auto-grade bets via NBA API
│   └── odds_cache.py              # API response caching
│
├── experiments/                   # EXPERIMENTAL CODE (not production)
│   ├── README.md                  # Experiments overview
│   ├── bolt_odds/                 # Bolt Odds WebSocket provider
│   │   ├── scanner.py             # Bolt Odds scanner
│   │   ├── bolt_bot.py            # Test Telegram bot
│   │   └── tests/                 # API tests
│   └── sportsgameodds/            # SportsGameOdds provider
│       ├── provider.py            # API client
│       ├── scanner.py             # Scanner implementation
│       ├── sgo_bot.py             # Test Telegram bot
│       └── config.py              # Test config
│
├── docs/                          # Documentation
│   ├── DECISIONS.md               # Architecture decisions
│   ├── ERRORS.md                  # Bug fixes log
│   └── TODO.md                    # Roadmap
│
├── .env                           # Production secrets (VPS only, not in git)
├── .env.test.example              # Test environment template
└── CLAUDE.md                      # This file
```

---

## VPS & Deployment

**Server:** 142.93.78.21 (SSH key auth, password: `25!?MooseHonse` if needed)

### Production Bot (TheOddsAPI)
```bash
# Deploy
ssh root@142.93.78.21 "cd /root/NBA-Long-Shot-Scanner-Bot && git pull && systemctl restart nba-longshot-bot"

# Status
ssh root@142.93.78.21 "systemctl status nba-longshot-bot"

# Logs
ssh root@142.93.78.21 "tail -f /root/NBA-Long-Shot-Scanner-Bot/src/bot.log"

# Stop
ssh root@142.93.78.21 "systemctl stop nba-longshot-bot"
```

### Bolt Odds Test Bot
```bash
# Deploy (runs in background)
ssh root@142.93.78.21 "cd /root/NBA-Long-Shot-Scanner-Bot/experiments/bolt_odds && pkill -f bolt_bot.py; nohup python3 bolt_bot.py > bolt_bot.log 2>&1 &"

# Logs
ssh root@142.93.78.21 "tail -f /root/NBA-Long-Shot-Scanner-Bot/experiments/bolt_odds/bolt_bot.log"

# Stop
ssh root@142.93.78.21 "pkill -f bolt_bot.py"
```

---

## Credentials

### Production (.env on VPS)
```
TELEGRAM_BOT_TOKEN=<production bot token>
TELEGRAM_CHAT_ID=5892910630
THEODDSAPI_KEY=<api key>
STATE=ny
```

### Experiments (hardcoded in files - test only)
| Provider | API Key Location |
|----------|------------------|
| Bolt Odds | `experiments/bolt_odds/scanner.py` line 40-41 |
| SportsGameOdds | `experiments/sportsgameodds/config.py` (awaiting key) |

**Test Telegram Channel:** `-1003336875829` (SGO_Test_Bot)

---

## Sportsbook Link Handling

**Supported States:** NY, PA, NJ (all shown in alerts for state-dependent books)

Different books require different URL formats for bet links to work:

| Book | State Required | URL Format | Alert Display |
|------|----------------|------------|---------------|
| **FanDuel** | Desktop only | `{state}.sportsbook.fanduel.com` | Desktop: NY · PA · NJ + Mobile link |
| **BetRivers** | Yes | `{state}.betrivers.com` | NY · PA · NJ |
| **BetMGM** | Yes | `sports.{state}.betmgm.com` | NY · PA · NJ |
| **BallyBet** | Yes | `{state}.ballybet.com` | NY · PA · NJ |
| **DraftKings** | No | `sportsbook.draftkings.com` | Single "Place Bet" link |

**Code Locations:**
- Production: `src/nba_value_scanner.py` - `generate_multi_state_links()` function
- Bolt Odds: `experiments/bolt_odds/scanner.py` lines 500-580

**Alert Display Examples:**

FanDuel (separate desktop/mobile):
```
🖥️ Desktop: NY · PA · NJ
📱 Mobile
```

BetRivers/BetMGM/BallyBet (same for desktop/mobile):
```
🔗 NY · PA · NJ
```

DraftKings (no state needed):
```
🔗 Place Bet
```

---

## Alert Tiers

| Tier | Emoji | Min Kelly | Min Coverage | Other |
|------|-------|-----------|--------------|-------|
| FIRE | 🔥 | 0.30 | 8 | - |
| VALUE_LONGSHOT | 🎯 | 0.15 | 5 | min_odds: +500 |
| OUTLIER | ⚡ | 0.05 | 3 | min_pct_vs_next: 35% |

---

## Markets (Longshots Only)

Currently scanning 10 longshot markets:
1. `player_double_double`
2. `player_triple_double`
3. `player_first_basket`
4. `player_first_team_basket`
5. `player_points_alternate`
6. `player_rebounds_alternate`
7. `player_assists_alternate`
8. `player_blocks_alternate`
9. `player_steals_alternate`
10. `player_threes_alternate`

Standard props (player_points, player_rebounds, etc.) are commented out for API cost savings.

---

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Show main menu |
| `/scan` | Manual scan |
| `/status` | Bot status and settings |
| `/setstate <XX>` | Change state for bet links (e.g., `/setstate nj`) |
| `/books` | Show legal sportsbooks for current state |
| `/roi` | View ROI statistics |
| `/help` | Show all commands |

---

## De-Vig Methodology

MKB V10 methodology:
- Hybrid 2-way/1-way calculation per book
- Global weights for book reliability (Pinnacle highest at 10)
- Market-specific multipliers for longshots
- Confidence adjustment based on coverage

---

## Working with Experiments

### Adding a New Odds Provider

1. Create directory: `experiments/<provider_name>/`
2. Required files:
   - `scanner.py` - Main scanner (same interface as `nba_value_scanner.py`)
   - `<name>_bot.py` - Test Telegram bot
   - `README.md` - Setup docs
3. Update `experiments/README.md` table
4. Test in SGO_Test_Bot channel

### Graduating to Production

When an experiment is ready:
1. Move scanner to `src/` or integrate with existing scanner
2. Add config options to `src/config.py`
3. Update `src/bot.py` to support new provider
4. Document in `docs/DECISIONS.md`
5. Archive or remove experiment directory

---

## Git Workflow

```bash
# Local development
git add . && git commit -m "message" && git push

# Deploy production
ssh root@142.93.78.21 "cd /root/NBA-Long-Shot-Scanner-Bot && git pull && systemctl restart nba-longshot-bot"

# Deploy test bot
ssh root@142.93.78.21 "cd /root/NBA-Long-Shot-Scanner-Bot && git pull && cd experiments/bolt_odds && pkill -f bolt_bot.py; nohup python3 bolt_bot.py > bolt_bot.log 2>&1 &"
```

---

## Project History

- **Original:** VPS at `/root/nba-value-bot/`
- **Jan 2026:** Migrated to GitHub
- **Jan 2026:** Reduced to longshot markets only (API savings)
- **Jan 2026:** Added dual FanDuel links (desktop/mobile)
- **Jan 2026:** Added experiments structure for Bolt Odds and SportsGameOdds testing
- **Jan 2026:** Added BetMGM and BallyBet state link handling
