# Experiments

This directory contains experimental odds providers and test implementations.

**Important:** Code in this directory is NOT production-ready. It's for testing new data sources, APIs, and approaches before potential integration into the main bot.

---

## Active Experiments

| Provider | Status | Description | Telegram Channel |
|----------|--------|-------------|------------------|
| [bolt_odds/](./bolt_odds/) | Testing | Real-time WebSocket odds via Bolt Odds API | SGO_Test_Bot |
| [sportsgameodds/](./sportsgameodds/) | Skeleton | REST/WebSocket provider for SportsGameOdds.com | SGO_Test_Bot |

---

## Directory Structure

```
experiments/
├── README.md                    # This file
├── bolt_odds/                   # Bolt Odds real-time WebSocket provider
│   ├── README.md                # Setup, API docs, status
│   ├── scanner.py               # Main scanner (WebSocket-based)
│   ├── bolt_bot.py              # Test Telegram bot
│   └── tests/                   # Connection and latency tests
│       ├── test_websocket.py
│       ├── test_nba_stream.py
│       └── ...
└── sportsgameodds/              # SportsGameOdds.com provider
    ├── README.md                # Setup, API docs, status
    ├── provider.py              # REST/WebSocket API client
    ├── scanner.py               # Scanner implementation
    ├── sgo_bot.py               # Test Telegram bot
    └── config.py                # Test-specific configuration
```

---

## Shared Test Environment

All experiments share a common test Telegram channel:

```
Bot Token: TEST_TELEGRAM_BOT_TOKEN (in .env.test)
Chat ID: -1003336875829 (SGO_Test_Bot channel)
```

---

## Running an Experiment

1. Navigate to the experiment directory
2. Read the experiment's README.md for setup
3. Configure `.env.test` in project root
4. Run the experiment's bot or test scripts

Example:
```bash
cd experiments/bolt_odds
python3 bolt_bot.py
```

---

## Adding a New Experiment

1. Create a new directory: `experiments/<provider_name>/`
2. Add a `README.md` with:
   - Provider description
   - API credentials location
   - Setup instructions
   - Current status
3. Implement the scanner and bot
4. Update this README's table

---

## Graduating to Production

When an experiment is ready for production:

1. Move core logic to `src/`
2. Add configuration to `config.py`
3. Update `CLAUDE.md` with new provider docs
4. Remove experiment directory (or archive)
5. Document the decision in `docs/DECISIONS.md`
