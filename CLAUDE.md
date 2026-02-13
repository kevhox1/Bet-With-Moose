# CLAUDE.md — Moose Bets (betwithmoose.com)

## PROJECT OVERVIEW

Moose Bets is a subscription-based web application for NBA player props sports betting. It provides a real-time odds screen with customizable fair value calculations, +EV highlighting, and deep links to sportsbooks. The product targets sharp recreational bettors who already use paid tools (Unabated, OddsJam, Betstamp Pro) and differentiates on price ($50/mo vs $79-500/mo), customization (3 fair value modes), latency (5-second refresh), and distinctive vintage sports card aesthetic.

**Domain:** betwithmoose.com
**Brand:** Moose Bets — vintage sports card aesthetic (warm, textured, craft feel with clean readable data)
**Launch Strategy:** 2 weeks free for all users → 7-day free trial for new users → $50/mo subscription via Stripe

---

## REFERENCE IMPLEMENTATION

A reference implementation exists at `./reference/` (copied from the NBA-Long-Shot-Scanner-Bot repo). This directory contains:
- Fair value calculation logic (sportsbook weighting and de-vig methodology)
- OddsBlaze API integration patterns (endpoints, params, response structure)
- Player/market normalization logic
- Both a TheOddsAPI implementation and an OddsBlaze implementation — **use the OddsBlaze code as the primary reference**

**Use this reference code to understand the existing fair value engine, de-vig method, and API patterns. Port the core calculation logic to the Python microservice.**

---

## TECH STACK

### Frontend
- **Framework:** React + Next.js (App Router, SSR for SEO/landing pages)
- **Data Table:** TanStack Table (headless — required for full design control over vintage aesthetic + virtual scrolling for performance)
- **Real-time:** WebSocket client (native browser WebSocket or socket.io-client)
- **Auth:** NextAuth.js (email/password + Google SSO providers)
- **Styling:** CSS Modules or Tailwind — must support the vintage sports card aesthetic. Desktop-first, functional on mobile.
- **State Management:** React Context or Zustand for global state (user preferences, WebSocket connection status)

### Backend — Hybrid Architecture
Two services communicate internally:

**Node.js Service (Fastify)**
- Real-time WebSocket server (pushes odds to all connected clients)
- REST API routing for frontend
- Auth / session management
- OddsBlaze API polling loop (every 5 seconds)
- Redis cache management
- Stripe webhook handler

**Python Service (FastAPI)**
- Fair value calculation engine (Mode 1: proprietary server-side computation)
- De-vig calculations (use method from reference repo)
- Dynamic market weighting engine
- CSV projection parsing (V2)
- Bet settlement / grading logic (V2)
- Called by Node service via internal REST API

**Communication:** Node calls Python service via internal HTTP (localhost or Docker network). Python service is NOT exposed to the internet.

### Database & Caching
- **PostgreSQL** — Users, user_preferences, sessions, odds_snapshots (V2: bet_tracking, fair_value_weight_configs)
- **Redis** — Hot odds cache (current odds for all markets), WebSocket pub/sub, rate limiting

### Infrastructure
- **Hosting:** Railway (MVP) — target ~$50-150/mo
  - Node service: Railway web service
  - Python service: Railway web service (internal only)
  - PostgreSQL: Railway managed Postgres
  - Redis: Railway managed Redis
- **Migration Path:** AWS (ECS or EC2) if scaling past 500 concurrent users
- **Domain/SSL:** betwithmoose.com — Railway provides automatic SSL via Let's Encrypt
- **Monitoring:**
  - UptimeRobot (free tier): Ping site every 5 minutes, SMS/email alert on downtime
  - OddsBlaze health check: Node service tracks last successful data fetch. If no fresh data for 30+ seconds, set `dataStale: true` flag → frontend shows "Data may be delayed" banner
  - Sentry (free tier): Error logging for both Node and Python services
- **Analytics:** Google Analytics (basic page views, session duration, user counts) + simple custom event tracking for key actions (filter usage, deep link clicks, sign-ups)

### Payments
- **Stripe Checkout** (hosted payment page — PCI compliant, trusted UX)
- Monthly only: $50/mo
- Built but dormant during 2-week free period
- No annual plan at launch

---

## DATA SOURCES

### OddsBlaze API (Primary — Odds Data)
- **Plan:** $250/mo subscription
- **Refresh:** Poll every 5 seconds (all sportsbooks in rotation)
- **Rate Limit:** 250 calls/min. Each call = all NBA odds from one sportsbook.
- **Polling Strategy:** With ~20 sportsbooks, one full cycle = ~20 calls. 250 ÷ 20 = 12.5 cycles/min ≈ 1 cycle every 4.8 seconds. Target 5-second refresh. No headroom for non-polling calls — all metadata/config calls should be cached aggressively or made at startup only.
- **Deep Links:** Included in API response for most sportsbooks. Use directly.
- **Results/Scores:** NOT available on current plan. Use nba_api for settlement (V2).

### Sportsbooks Available (Include ALL in scanner)
Active in scanner:
- DraftKings
- FanDuel
- BetMGM
- Caesars
- Hard Rock
- Fliff
- Bet365
- Fanatics
- Bally Bet
- BetParx
- BetRivers
- ProphetX
- Pinnacle
- TheScore
- FanDuel YourWay
- Circa

**Excluded from MVP:** Polymarket (prediction market, different odds structure), hard-rock-illinois, hard-rock-indiana, betmgm-michigan, bwin, sports-interaction, betonline, bovada, bodog, kalshi

### Player Prop Markets Available (Include ALL)
- Player Points (21 books)
- Player Rebounds (21 books)
- Player Assists (20 books)
- Player Threes Made (20 books)
- Player Points + Rebounds + Assists (18 books)
- Player Double Double (17 books)
- Player Blocks (16 books)
- Player Points + Assists (14 books)
- Player Points + Rebounds (14 books)
- Player Rebounds + Assists (14 books)
- Player Steals (12 books)
- Player Triple Double (10 books)
- Player Blocks + Steals (9 books)
- 1st Quarter Player Points (9 books)
- 1st Quarter Player Assists (8 books)
- 1st Quarter Player Rebounds (8 books)
- First Field Goal (8 books)
- First Basket (7 books)
- Away Team First Field Goal (5 books)
- Home Team First Field Goal (5 books)
- Player Field Goals Made (3 books)
- 1st 3 Minutes Player Points (2 books)
- 1st 3 Minutes Player Assists (1 book)
- 1st 3 Minutes Player Rebounds (1 book)

### Settlement Data (V2 — not MVP)
- **Primary:** nba_api (Python library) — individual player stat lines
- **Fallback:** balldontlie API
- **Schedule:** Hourly cron job post-game. 1-hour delay for NBA stat corrections.

---

## CORE DATA MODEL

### Odds Screen Table Structure

**One row per player + market.** Sportsbook odds displayed as sub-columns across the row.

Example row:
```
| Game | Player | Bet Type | Line | DK | FD | BetMGM | Caesars | ... | Best Odds | Fair Value | Edge % | Kelly Size |
| NYK @ BOS | Jalen Brunson | Points Over | 24.5 | -110 | -108 | -105 | -112 | ... | -105 (BetMGM) | -107 | 2.3% | $45 |
```

**When the same player+market has different lines across books (e.g., DK has 24.5, BetMGM has 25.5), create separate rows — one per distinct line.**

### MVP Columns
| Column | Description | Source |
|--------|-------------|--------|
| Game | Matchup (e.g., "NYK @ BOS") | OddsBlaze |
| Player | Player name | OddsBlaze |
| Date | Game date | OddsBlaze |
| Bet Type | Market + direction (e.g., "Points Over") | OddsBlaze |
| Line | The number (e.g., 24.5) | OddsBlaze |
| [Sportsbook columns] | American odds per book (e.g., -110) | OddsBlaze |
| Best Available Odds | Best odds across all books, with book identified | Computed |
| Fair Value | De-vigged fair value line/odds | Python service (Mode 1) |
| Edge % | Difference between best available implied prob and fair value implied prob | Computed |
| Kelly Bet Size | Recommended bet based on user bankroll × Kelly fraction × edge | Computed (client-side, uses user profile) |
| Sportsbook (for best odds) | Which book has the best odds | Computed |
| Last Updated | Timestamp of most recent odds update | OddsBlaze |

### Sportsbook Sub-Columns Behavior
- On first load (no user preferences): Show ALL sportsbooks. User scrolls horizontally.
- After user sets preferred sportsbooks in profile: Only show preferred books as columns. Other books still factor into "Best Available Odds" calculation.
- Each sportsbook column cell is clickable → opens deep link to that sportsbook's bet slip in new tab.

### +EV Highlighting
- **Default:** Only show rows where Edge % > 0 (positive EV). Negative EV rows filtered out by default.
- **Color coding by edge magnitude:**
  - 0-2% edge: Subtle warm highlight (muted green/gold in vintage palette)
  - 2-5% edge: Stronger highlight
  - 5%+ edge: Bold/prominent treatment
- **User can toggle to show all rows** (including negative EV, which appear muted/grayed)

### Filters (MVP)
- Game (dropdown: tonight's games)
- Player (search/autocomplete)
- Bet Type (dropdown: all available market types)
- Sportsbook (multi-select: filter which books to display)
- Minimum Edge % (slider or input: e.g., "only show 2%+ edge")

---

## FAIR VALUE SYSTEM

### Mode 1: Proprietary Moose Bets Fair Value (MVP)
- **Computation:** Server-side only (Python service). Weights are NEVER exposed to the client.
- **Method:** Port the fair value logic from `./reference/`. This includes:
  - De-vig method (check reference repo for exact implementation)
  - Sportsbook weighting (check reference repo for weight assignments)
- **Flow:** OddsBlaze raw odds → Node server → forwarded to Python service → Python computes fair value for each market → returns fair value + edge calculations → Node caches in Redis → pushed to clients via WebSocket
- **Update frequency:** Recomputed on every 5-second poll cycle

### Mode 2: Custom Sportsbook Weights (V2)
- User sets percentage weights per sportsbook (e.g., Pinnacle 40%, DraftKings 20%, etc.)
- Computed CLIENT-SIDE (user's personalized weights stay on their device)
- UI: Sliders or input fields per book, must sum to 100%

### Mode 3: User-Imported Projections (V2)
- User uploads CSV with their own mean projections per player per stat
- Template provided (player_name, stat_type, projection)
- System converts projections to implied probabilities for each line
- **Market regression option:** Blend user projections with market fair value (e.g., 70% user projection / 30% market). Slider controls the blend.
- Computed CLIENT-SIDE

---

## USER SYSTEM

### Authentication
- **NextAuth.js** with two providers:
  - Email/password (with bcrypt hashing)
  - Google SSO
- Session stored in PostgreSQL (or JWT — NextAuth default)

### User Profile (stored in PostgreSQL)
```
users:
  - id (uuid)
  - email
  - name
  - created_at
  - subscription_status (free | trial | active | cancelled)
  - stripe_customer_id

user_preferences:
  - user_id (FK)
  - preferred_sportsbooks (array of sportsbook keys)
  - bankroll (decimal, in dollars)
  - kelly_fraction (decimal, default 0.25 = quarter Kelly)
  - min_edge_threshold (decimal, default 0.0)
  - show_negative_ev (boolean, default false)
```

### Kelly Bet Size Calculation (Client-Side)
```
kelly_fraction_from_profile = user.kelly_fraction (default 0.25)
edge = (fair_value_implied_prob - best_odds_implied_prob) / best_odds_implied_prob
kelly_bet = bankroll × kelly_fraction × edge
```
Display as dollar amount in the Kelly Bet Size column. If user hasn't set bankroll, show "Set bankroll" link instead.

---

## REAL-TIME DATA FLOW

```
┌─────────────┐     REST (5s poll)      ┌──────────────┐
│  OddsBlaze   │ ─────────────────────► │  Node Server  │
│    API       │                         │  (Fastify)    │
└─────────────┘                         │               │
                                        │  ┌──────────┐ │
                                        │  │  Redis    │ │  Internal HTTP
                                        │  │  Cache    │ │ ──────────────►  ┌──────────────┐
                                        │  └──────────┘ │                   │  Python Svc   │
                                        │               │ ◄──────────────── │  (FastAPI)    │
                                        │  ┌──────────┐ │   Fair values     │  Fair value   │
                                        │  │ WebSocket │ │                   │  engine       │
                                        │  │  Server   │ │                   └──────────────┘
                                        │  └────┬─────┘ │
                                        └───────┼───────┘
                                                │ WebSocket push
                                    ┌───────────┼───────────┐
                                    ▼           ▼           ▼
                                 Client 1   Client 2   Client N
```

### Polling Loop (Node Server)
1. Every 5 seconds, cycle through all active sportsbooks
2. For each book, call OddsBlaze API → get all NBA player prop odds
3. Normalize and merge into unified data structure keyed by `{player_id}_{market_type}_{line}`
4. Send batch to Python service for Mode 1 fair value computation
5. Python returns fair values + edge calculations
6. Update Redis cache with fresh data
7. Push full odds snapshot to all connected WebSocket clients

### WebSocket Protocol
- Client connects on auth → receives full odds snapshot
- Every 5 seconds: server pushes delta update (only changed odds) or full snapshot
- Client renders TanStack Table from latest data
- If no update received in 30 seconds → client shows "Data may be delayed" warning

### Error Handling
- **OddsBlaze down:** Continue serving last known data from Redis. Show "Data delayed — last updated X minutes ago" banner. Set `dataStale` flag when no successful fetch for 30+ seconds.
- **Python service down:** Serve odds without fair value calculations. Show "Fair value temporarily unavailable" for those columns.
- **WebSocket disconnect:** Client auto-reconnects with exponential backoff. Show "Reconnecting..." indicator.
- **Invalid/missing data:** Never crash. Show empty cells or "N/A" for missing data points.

---

## PAGES & ROUTES

### Public Routes (no auth required)
- `/` — Landing page with blurred/limited odds screen preview + sign-up CTA
- `/login` — Login page (email/password + Google SSO)
- `/signup` — Registration page
- `/how-it-works` — Education articles template page
- `/terms` — Terms of Service (placeholder)
- `/privacy` — Privacy Policy (placeholder)

### Protected Routes (auth required)
- `/dashboard` — Main odds screen (the core product)
- `/profile` — User preferences (preferred sportsbooks, bankroll, Kelly fraction)
- `/account` — Subscription management (Stripe customer portal link)

### Landing Page (`/`)
- Vintage sports card aesthetic hero section
- Value proposition: "Real-time NBA player props odds with customizable fair value. Find +EV bets faster."
- Blurred/limited preview of the actual odds screen (show real data but blur sportsbook columns and fair value — enough to see what the tool does, not enough to use it)
- Sign-up CTA
- Feature highlights (speed, customization, deep links, price comparison)
- Responsible gambling footer

### Legal Footer (every page)
```
Moose Bets is not a sportsbook. For informational and entertainment purposes only.
Past performance does not guarantee future results.
Must be 21+ to use this site. Please gamble responsibly.
National Problem Gambling Helpline: 1-800-GAMBLER
```

---

## SUBSCRIPTION & PAYWALL

### Phase 1: Free Period (Weeks 1-2 post-launch)
- All users have full access after sign-up
- Stripe integration built but not enforced
- Collect emails for marketing

### Phase 2: Paid Model (Week 3+)
- New users: 7-day free trial → $50/mo
- Existing free users: Prompted to subscribe. Free access revoked.
- **Free tier (post-paywall):** Users who don't subscribe see the blurred/limited landing page view. They cannot access `/dashboard`.

### Stripe Integration
- Use Stripe Checkout (hosted) for payment
- Stripe Customer Portal for subscription management (cancel, update payment)
- Webhook handler in Node service for:
  - `checkout.session.completed` → activate subscription
  - `customer.subscription.updated` → update status
  - `customer.subscription.deleted` → revoke access
  - `invoice.payment_failed` → flag account, send email

---

## AESTHETIC & DESIGN DIRECTION

### Vintage Sports Card Theme
- **Feel:** Warm, textured, craft-like. Think classic Topps baseball cards meets Bloomberg terminal data.
- **Color palette:** Warm tones — cream/off-white backgrounds, deep burgundy/forest green/navy accents, gold highlights for +EV. Muted tones for negative/neutral data.
- **Typography:** Mix of a display/serif font for headers/branding (vintage feel) and a clean mono/sans-serif for data cells (readability)
- **Data table:** Clean, readable, high-density. The vintage aesthetic applies to the chrome/frame/branding AROUND the table, not to the table cells themselves. Data must be scannable.
- **+EV highlighting:** Warm gold/green gradient that fits the vintage palette — NOT neon/hacker green
- **Deep link buttons:** Sportsbook logos or abbreviated names in each cell, clickable
- **Responsiveness:** Desktop-first. On mobile, the table scrolls horizontally. Key columns (Player, Bet Type, Line, Best Odds, Edge %) should be sticky/frozen on the left.

---

## MVP FEATURE CHECKLIST

### Must Ship (Weeks 1-3)
- [ ] Landing page with vintage aesthetic, blurred odds preview, sign-up CTA
- [ ] Auth: email/password + Google SSO (NextAuth.js)
- [ ] Odds screen: TanStack Table, all columns defined above
- [ ] Real-time: Node polls OddsBlaze every 5s, WebSocket push to clients
- [ ] Fair Value Mode 1: Python service computes proprietary fair value (port from reference repo)
- [ ] +EV highlighting: color-coded by edge magnitude
- [ ] Deep links: click sportsbook odds cell → opens bet slip in new tab
- [ ] Filters: Game, Player, Bet Type, Sportsbook, minimum Edge %
- [ ] User profile: preferred sportsbooks, bankroll, Kelly fraction
- [ ] Kelly bet size column (client-side calculation)
- [ ] All ~16 sportsbooks as columns, horizontal scroll, sticky left columns on mobile
- [ ] Responsive layout: desktop-first, functional on mobile
- [ ] How It Works page (template, content provided later)
- [ ] Legal pages: placeholder ToS, Privacy Policy
- [ ] Responsible gambling footer on every page
- [ ] Stripe Checkout integration (built, dormant during free period)
- [ ] Error handling: graceful degradation for all failure modes
- [ ] UptimeRobot monitoring
- [ ] OddsBlaze health check (30-second stale data threshold → banner)
- [ ] Sentry error logging (Node + Python)
- [ ] Google Analytics (page views, session duration, key events)
- [ ] 21+ age gate on first visit (modal or interstitial)

### V2 Backlog (Weeks 4-8)
- [ ] Fair Value Mode 2: custom sportsbook weights (client-side)
- [ ] Fair Value Mode 3: CSV projection upload with market regression (client-side)
- [ ] Bet tracking: deep link click → save bet modal → auto-fill
- [ ] Auto-settlement: nba_api → hourly cron → grade bets
- [ ] Profile analytics: ROI, units won/lost, win rate, CLV
- [ ] Pre-built views: Best Bets, Player Card, Game View, Sportsbook View
- [ ] On-site alert system for +EV threshold triggers
- [ ] Dynamic market weighting with performance logging
- [ ] Line movement history / odds snapshots table
- [ ] Hold % column
- [ ] Movement indicator column (line trending up/down)
- [ ] Full vintage aesthetic polish pass
- [ ] Mobile optimization pass
- [ ] Education content buildout (8-10 articles)
- [ ] Moose Bets Discord community

---

## PROJECT STRUCTURE (Recommended)

```
moose-bets/
├── CLAUDE.md                    # This file
├── README.md
├── .env.example                 # Environment variable template
├── docker-compose.yml           # Local dev: Node + Python + Postgres + Redis
│
├── frontend/                    # Next.js application
│   ├── package.json
│   ├── next.config.js
│   ├── public/
│   │   └── images/              # Logos, vintage textures, sportsbook icons
│   ├── src/
│   │   ├── app/                 # Next.js App Router pages
│   │   │   ├── page.tsx         # Landing page (/)
│   │   │   ├── login/
│   │   │   ├── signup/
│   │   │   ├── dashboard/       # Main odds screen
│   │   │   ├── profile/
│   │   │   ├── account/
│   │   │   ├── how-it-works/
│   │   │   ├── terms/
│   │   │   └── privacy/
│   │   ├── components/
│   │   │   ├── OddsTable/       # TanStack Table + columns + highlighting
│   │   │   ├── Filters/         # Filter bar components
│   │   │   ├── Layout/          # Header, footer, navigation
│   │   │   ├── Auth/            # Login/signup forms
│   │   │   ├── Profile/         # Preference forms
│   │   │   └── ui/              # Shared UI primitives (buttons, modals, badges)
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts  # WebSocket connection + auto-reconnect
│   │   │   ├── useOddsData.ts   # Odds state management
│   │   │   └── useAuth.ts       # Auth state
│   │   ├── lib/
│   │   │   ├── kelly.ts         # Kelly criterion calculation
│   │   │   ├── ev.ts            # Edge % / implied probability helpers
│   │   │   ├── formatting.ts    # Odds formatting (American ↔ decimal ↔ implied prob)
│   │   │   └── api.ts           # API client
│   │   ├── styles/
│   │   │   └── vintage-theme/   # Vintage sports card CSS/tokens
│   │   └── types/
│   │       └── odds.ts          # TypeScript types for odds data
│   └── tsconfig.json
│
├── server/                      # Node.js (Fastify) service
│   ├── package.json
│   ├── src/
│   │   ├── index.ts             # Server entry point
│   │   ├── config/
│   │   │   └── env.ts           # Environment config
│   │   ├── routes/
│   │   │   ├── auth.ts          # Auth endpoints
│   │   │   ├── user.ts          # User profile endpoints
│   │   │   └── stripe.ts        # Stripe webhook handler
│   │   ├── services/
│   │   │   ├── oddsblaze.ts     # OddsBlaze polling loop
│   │   │   ├── fairvalue.ts     # Calls Python service for fair value
│   │   │   ├── websocket.ts     # WebSocket server + broadcast
│   │   │   └── redis.ts         # Redis cache operations
│   │   ├── middleware/
│   │   │   ├── auth.ts          # JWT/session validation
│   │   │   └── subscription.ts  # Paywall check
│   │   └── types/
│   │       └── odds.ts          # Shared types
│   └── tsconfig.json
│
├── calculator/                  # Python (FastAPI) microservice
│   ├── requirements.txt
│   ├── main.py                  # FastAPI entry point
│   ├── routers/
│   │   └── fairvalue.py         # Fair value computation endpoints
│   ├── services/
│   │   ├── devig.py             # De-vig calculations (port from reference repo)
│   │   ├── weights.py           # Sportsbook weighting logic (port from reference repo)
│   │   └── market.py            # Market data processing
│   └── models/
│       └── schemas.py           # Pydantic models
│
├── database/
│   └── migrations/              # SQL migration files
│       ├── 001_users.sql
│       ├── 002_user_preferences.sql
│       └── 003_odds_snapshots.sql
│
└── scripts/
    ├── seed.sh                  # Dev seed data
    └── deploy.sh                # Railway deploy script
```

---

## ENVIRONMENT VARIABLES

```env
# OddsBlaze
ODDSBLAZE_API_KEY=<your-key>
ODDSBLAZE_BASE_URL=<api-base-url>
ODDSBLAZE_POLL_INTERVAL_MS=5000

# Database
DATABASE_URL=postgresql://user:pass@host:5432/moosebets

# Redis
REDIS_URL=redis://host:6379

# Auth
NEXTAUTH_SECRET=<random-secret>
NEXTAUTH_URL=https://betwithmoose.com
GOOGLE_CLIENT_ID=<google-oauth-client-id>
GOOGLE_CLIENT_SECRET=<google-oauth-client-secret>

# Stripe
STRIPE_SECRET_KEY=<stripe-secret>
STRIPE_PUBLISHABLE_KEY=<stripe-publishable>
STRIPE_WEBHOOK_SECRET=<stripe-webhook-secret>
STRIPE_PRICE_ID=<stripe-monthly-price-id>

# Python Service
CALCULATOR_SERVICE_URL=http://localhost:8001

# Monitoring
SENTRY_DSN_NODE=<sentry-dsn>
SENTRY_DSN_PYTHON=<sentry-dsn>

# Feature Flags
PAYWALL_ENABLED=false  # Flip to true when free period ends
FREE_TRIAL_DAYS=7
```

---

## CRITICAL IMPLEMENTATION NOTES

1. **Never expose Mode 1 fair value weights to the client.** The proprietary sportsbook weights must stay server-side in the Python service. The client receives only the computed fair value number, not the inputs.

2. **OddsBlaze rate limit is tight.** 250 calls/min with ~20 books = exactly one 5-second cycle. Do NOT make any additional OddsBlaze API calls outside the main polling loop. Cache all metadata at startup.

3. **Player/market normalization:** OddsBlaze should provide normalized player IDs and market keys across sportsbooks. Verify this. If not, build a normalization layer that maps inconsistent names to canonical IDs (e.g., "J. Brunson" → "Jalen Brunson").

4. **Alt lines create separate rows.** If DraftKings has "Brunson Points O 24.5" and BetMGM has "Brunson Points O 25.5", these are TWO rows in the table, not one. Group by player+market+line.

5. **Deep links open in new tabs.** Never navigate the user away from Moose Bets. Use `target="_blank"` with `rel="noopener noreferrer"`.

6. **Kelly bet size requires bankroll.** If the user hasn't set their bankroll in profile, show a "Set bankroll →" link in the Kelly column instead of a number. Default Kelly fraction is 0.25 (quarter Kelly).

7. **The vintage aesthetic goes on the chrome, not the data.** Headers, nav, branding, page borders = vintage. Data table cells = clean, high-density, scannable. Don't sacrifice readability for style inside the table.

8. **Graceful degradation is mandatory.** This is a solo-operated product. Every external dependency failure must result in a user-friendly state, never a crash or blank screen.

9. **Polymarket is excluded from MVP.** Do not include Polymarket data in the scanner or fair value calculations.

10. **Horizontal scroll for sportsbook columns is expected.** All ~16 sportsbooks appear as columns. Desktop users scroll right. On mobile, Player/Bet Type/Line/Best Odds/Edge% columns should be sticky on the left.

---

## COMPETITIVE CONTEXT

Moose Bets competes with:
- **Unabated (~$99/mo):** Proprietary "Unabated Line," projection imports, Discord community. Lacks: prop coverage depth, mobile app, automated alerts (except top tier).
- **OddsJam ($79-299/mo):** Widest market coverage, good alerts. Lacks: custom fair value, rigid EV calculation.
- **Betstamp Pro ($150-500/mo):** 150+ sportsbook feeds, drag-and-drop UI, dynamically weighted true line. Lacks: expensive, application-only, targets professionals.
- **OddsShopper/Portfolio EV (~$100/mo):** Transparent results, "betting as investing." Lacks: less customizable, casual-focused.

**Moose Bets differentiators:** Lower price ($50/mo), 3 fair value modes (vs competitors' single approach), vintage aesthetic (unique in sterile fintech market), OddsBlaze latency, CSV projection import.
