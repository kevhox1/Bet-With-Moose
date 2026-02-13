# TODO

Prioritized list of remaining work.

---

## High Priority

- [ ] **Fix hardcoded API key** - `src/nba_value_scanner.py` line 25 has hardcoded TheOddsAPI key. Should use `config.THEODDSAPI_KEY` instead.

---

## Medium Priority

- [ ] **Add link transformations for other sportsbooks** - Currently only FanDuel has desktop/mobile link variants. Could add similar logic for DraftKings, BetMGM, etc. if their deep links have device-specific requirements.

---

## Low Priority / Cleanup

- [ ] **Remove old bot code from VPS** - Legacy code exists at `/root/nba-value-bot/` (not running). Can be deleted to free space.

- [ ] **Add tests** - No test suite currently. Could add unit tests for de-vig calculations and alert tier logic.

---

## Completed

- [x] Migrate to GitHub repository (Jan 2026)
- [x] Set up proper .env configuration (Jan 2026)
- [x] Reduce to longshot markets only (Jan 2026)
- [x] Add dual FanDuel links for desktop/mobile (Jan 2026)
- [x] Add default active hours 8AM-12AM EST (Jan 2026)
