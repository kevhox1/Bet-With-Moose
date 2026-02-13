# Architecture Decisions

This document logs significant architectural choices made during development.

---

## 2026-01-22: Default Active Hours Changed to 8AM-12AM EST

**Decision:** Scanner defaults to running only from 8AM to midnight EST, auto-pausing from midnight to 8AM.

**Rationale:** NBA games typically occur in the evening/night. Running the scanner 24/7 wastes API calls during hours when no games are happening. Users can still manually `/resume` during off-hours if needed.

**Files changed:** `config.py`, `.env.example`, `bot.py` (status display)

---

## 2026-01 (Migration): GitHub Repository Structure

**Decision:** Migrated from VPS-only development to GitHub with clean `src/` architecture.

**Rationale:** Version control, easier collaboration with Claude Code, backup, and ability to work locally then deploy.

**Structure:**
```
src/           - All Python source code
docs/          - Documentation (decisions, errors, todos)
.env.example   - Template for environment variables
CLAUDE.md      - Context for AI assistance
```

---

## 2026-01: Longshot Markets Only

**Decision:** Reduced from 21 markets to 10 longshot-only markets.

**Rationale:** API cost savings. Standard props (points, rebounds, assists) have high volume but lower edge. Longshots (double-doubles, first basket, alternates) have better +EV opportunities with fewer API calls.

**Location:** `src/nba_value_scanner.py` lines 30-42

---

## 2026-01: Dual FanDuel Links (Desktop + Mobile)

**Decision:** Show both desktop and mobile FanDuel deep links in alerts.

**Rationale:** FanDuel requires state prefix for desktop (`pa.sportsbook.fanduel.com`) but not for mobile. Showing both ensures links work regardless of device.

**Location:** `src/nba_value_scanner.py` lines 563-573, 990-992

---

## Original: MKB V10 De-Vig Methodology

**Decision:** Use hybrid 2-way/1-way de-vig with global book weights and market-specific multipliers.

**Rationale:** More accurate fair value calculation than simple average. Weights Pinnacle highest as sharpest book. Longshot multipliers account for different market dynamics.

**Location:** `src/nba_value_scanner.py`
