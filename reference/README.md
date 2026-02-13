# NBA Long Shot Scanner Bot

A Telegram bot that scans for NBA betting value opportunities using TheOddsAPI. It identifies longshot bets with positive expected value (+EV) across multiple sportsbooks and sends alerts to your Telegram chat.

## Features

- **Value Scanning**: Automatically scans for +EV betting opportunities across NBA player props and game markets
- **Multi-Sportsbook Support**: Compares odds across DraftKings, FanDuel, BetMGM, Caesars, ESPN Bet, and more
- **State-Aware**: Filters alerts to only show books legal in your state
- **Alert Tiers**: Categorizes opportunities as FIRE, VALUE_LONGSHOT, or OUTLIER
- **Bet Logging**: Tracks all sent alerts for ROI analysis
- **Auto-Grading**: Automatically grades bets using NBA API game results
- **Odds Caching**: Reduces API calls by caching odds data

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/NBA-Long-Shot-Scanner-Bot.git
cd NBA-Long-Shot-Scanner-Bot
```

### 2. Create virtual environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your credentials:
- `TELEGRAM_BOT_TOKEN`: Get from [@BotFather](https://t.me/BotFather)
- `TELEGRAM_CHAT_ID`: Your Telegram chat ID
- `THEODDSAPI_KEY`: Get from [TheOddsAPI](https://the-odds-api.com/)
- `STATE`: Your two-letter state code (e.g., `pa`, `nj`, `ny`)

### 5. Run the bot

```bash
cd src
python bot.py
```

## Project Structure

```
NBA-Long-Shot-Scanner-Bot/
├── src/
│   ├── bot.py              # Main Telegram bot with scheduler
│   ├── config.py           # Configuration and settings
│   ├── database.py         # SQLite database for alerts/settings
│   ├── nba_value_scanner.py # Core odds scanning logic
│   ├── bet_logger.py       # Bet logging for ROI tracking
│   ├── bet_grader.py       # Auto-grading using NBA API
│   └── odds_cache.py       # Odds API response caching
├── .env.example            # Environment variables template
├── .gitignore
├── requirements.txt
└── README.md
```

## Bot Commands

- `/start` - Start the bot and show menu
- `/scan` - Run a manual scan for opportunities
- `/status` - Check bot status and settings
- `/setstate <state>` - Change your state (e.g., `/setstate nj`)
- `/roi` - View ROI statistics
- `/help` - Show available commands

## Deployment

### Systemd Service (Linux)

Create `/etc/systemd/system/nba-value-bot.service`:

```ini
[Unit]
Description=NBA Value Alert Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/path/to/NBA-Long-Shot-Scanner-Bot/src
ExecStart=/path/to/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable nba-value-bot
sudo systemctl start nba-value-bot
```

## License

Private use only.
