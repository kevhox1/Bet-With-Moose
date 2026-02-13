# OddsBlaze NBA Scanner Bot

Real-time NBA player props scanner using OddsBlaze API with Telegram alerts.

## Features

- **14 Sportsbooks**: DraftKings, FanDuel, BetMGM, Caesars, BetRivers, Fanatics, betPARX, Fliff, theScore, Pinnacle, Circa, bet365, Bovada, Hard Rock
- **Deep Links**: Direct bet links from OddsBlaze API
- **De-vig**: Uses Pinnacle/Circa for fair value calculation
- **Alternate Lines**: Full alternate player prop coverage
- **Alert Tiers**: 🔥 FIRE, 🎯 VALUE_LONGSHOT, ⚡ OUTLIER

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot
python oddsblaze_bot.py
```

## Configuration

Edit `oddsblaze_bot.py` to change:

| Setting | Default | Description |
|---------|---------|-------------|
| `API_KEY` | (set) | OddsBlaze API key |
| `TELEGRAM_BOT_TOKEN` | (set) | Telegram bot token |
| `TELEGRAM_CHAT_ID` | (set) | Channel to send alerts |
| `SCAN_INTERVAL_SECONDS` | 30 | Auto-scan frequency |

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Main menu with buttons |
| `/scan` | Manual scan |
| `/status` | Bot status |
| `/help` | Help message |

## Alert Tiers

| Tier | Emoji | Criteria |
|------|-------|----------|
| FIRE | 🔥 | Kelly 30%+, 8+ books |
| VALUE_LONGSHOT | 🎯 | Kelly 15%+, 5+ books, +500 odds |
| OUTLIER | ⚡ | Kelly 5%+, 35%+ better than next |

## Sportsbooks

### Retail Books (alerts enabled)
- DraftKings
- FanDuel
- BetMGM
- Caesars
- BetRivers
- Fanatics
- betPARX
- Fliff
- theScore
- bet365
- Hard Rock

### Coverage-only (no alerts, count in coverage)
- Pinnacle (sharp - used for de-vig)
- Circa (sharp - used for de-vig)
- Bovada (offshore - coverage only)

## Data Source

[OddsBlaze](https://oddsblaze.com) - Real-time sports betting odds API
