# Bet-With-Moose QA Notes — 2026-02-14

## Live URLs
- **Frontend:** https://frontend-production-d029.up.railway.app
- **Server:** https://server-production-e527.up.railway.app

## ✅ Working
- Registration, login, duplicate email rejection
- JWT auth flow (profile, preferences CRUD)
- Odds API returns 1,248 rows (Mavs @ Lakers props from fanduel-yourway)
- Frontend renders, nav works, filters render
- SQL injection attempts handled safely (parameterized queries)
- Graceful error messages for malformed requests on server side
- WebSocket server initialized (attached to Fastify HTTP server)

## 🐛 Bugs to Fix

### 1. Frontend shows "No +EV bets found" even though API has 1,248 rows
- **Root cause:** All rows have `edgePct: null` because calculator can't compute fair values with only 1 book (fanduel-yourway). The filter `(r.edgePct ?? 0) > 0` treats null as 0, filtering everything out.
- **Fix:** Smarter empty state — detect when rows exist but none are +EV and show a message like "1,248 props available but no +EV edges detected (only 1 sportsbook reporting). Check 'Show All' to browse raw odds."
- **File:** `frontend/src/components/OddsTable/OddsTable.tsx` + `frontend/src/hooks/useOddsData.ts`

### 2. Frontend error messages are generic ("Request failed")
- **Root cause:** `api.ts` reads `err.message` but server returns `{ error: "..." }`. Users always see "Request failed" instead of actual error.
- **Fix:** Change error extraction in `api.ts`:
  ```js
  throw new Error(err.error || err.message || 'Request failed');
  ```
- **File:** `frontend/src/lib/api.ts`

### 3. XSS vulnerability — name field accepts raw HTML/script tags
- **Root cause:** No server-side sanitization on registration name field.
- **Fix:** Strip HTML tags from name in auth register route.
- **File:** `server/src/routes/auth.ts`

### 4. No input validation on registration
- No email format check (can register with "a" as email)
- No name length limit
- **Fix:** Add basic regex email validation, max name length (100 chars)
- **File:** `server/src/routes/auth.ts`

### 5. No rate limiting on auth endpoints
- Brute force login possible
- **Fix:** Add `@fastify/rate-limit` plugin, limit auth routes to ~10 req/min per IP
- **File:** `server/src/index.ts` + `server/src/routes/auth.ts`

### 6. Calculator returns null fair values
- Only 1 book reporting (fanduel-yourway) → 2-way devig needs opposite side, 1-way should still work but seems to not be
- Need to debug calculator service logs on Railway to see if it's being called at all or erroring
- **File:** `server/src/services/fairvalue.ts`, `calculator/services/market.py`

### 7. No /health endpoint (only /api/health)
- Minor — conventional for load balancers/monitoring
- **File:** `server/src/routes/odds.ts`

### 8. Stale data flag not accurate
- `dataStale: false` even during All-Star break because server keeps re-polling the same stale OddsBlaze data
- Should check if game dates are in the past
- **File:** `server/src/services/oddsblaze.ts`

## 🔧 Priority Order
1. Fix error message parsing in api.ts (30 sec, big UX win)
2. Smarter empty state on dashboard (users think app is broken)
3. Debug calculator → fair value pipeline (core value prop)
4. XSS sanitization + input validation
5. Rate limiting
6. Stale data detection
7. Health endpoint
