# Errors & Solutions

This document logs bugs encountered and how they were resolved.

---

## Template

```
## [Date]: Brief description

**Error:** What happened
**Cause:** Why it happened
**Solution:** How it was fixed
**Files:** Which files were changed
```

---

## 2026-01: FanDuel Desktop Links Not Working

**Error:** FanDuel deep links opened to homepage instead of adding bet to slip on desktop browsers.

**Cause:** FanDuel desktop site requires state prefix in URL (e.g., `pa.sportsbook.fanduel.com`) while mobile does not.

**Solution:** Added logic to generate both desktop (with state prefix) and mobile (original) links. Both are displayed in alerts.

**Files:** `src/nba_value_scanner.py`

---

## 2026-01: Bot Not Starting After Migration

**Error:** Bot failed to start on VPS after GitHub migration.

**Cause:** `.env` file was in `.gitignore` (correctly) but didn't exist on VPS after fresh clone.

**Solution:** Created `.env` on VPS with credentials. Added `.env.example` to repo as template.

**Files:** `.env.example` (created), VPS `.env` (created manually)

---
