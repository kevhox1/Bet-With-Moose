# Moose Bets — Agent Architecture & Work Breakdown

## Overview

This project uses a coordinated multi-agent approach with Bujar (main session) as Engineering Lead, a Moose Ops coordinator agent, and specialized worker agents.

## Agent Structure

```
Kevin (Product Owner)
  ↕
Bujar (Engineering Lead — main session)
  ↕
🎯 Moose Ops (Coordinator Agent)
  ├── 🐍 Python Engine Agent — Fair value service (FastAPI)
  ├── ⚡ Node Backend Agent — Real-time server (Fastify + WebSocket)
  ├── 🎨 Frontend Agent — UI (Next.js + TanStack Table)
  └── 🔧 DevOps Agent — Docker, Railway, DB, CI/CD
```

## Phase 1: Foundation (Week 1)

### 🐍 Python Engine Agent
**Mission:** Port the fair value calculation engine from reference repo to a standalone FastAPI microservice.

**Scope:**
- Port `nba_value_scanner.py` de-vig logic (hybrid 2-way/1-way methodology)
- Port sportsbook weighting system (GLOBAL_WEIGHTS)
- Port confidence multipliers, Kelly calculations
- Create FastAPI endpoints:
  - `POST /fair-value` — accepts raw odds, returns fair value + edge + Kelly
  - `GET /health` — health check
- Adapt from TheOddsAPI data format to OddsBlaze data format
- Unit tests for all calculation functions
- Docker containerization

**Key Reference Files:**
- `reference/src/nba_value_scanner.py` — core calculation logic
- `reference/src/config.py` — configuration patterns

**Critical Constraints:**
- Weights must NEVER be exposed to clients
- Must handle missing data gracefully (partial book coverage)
- Must support all market types listed in CLAUDE.md

### ⚡ Node Backend Agent
**Mission:** Build the Fastify server with OddsBlaze polling, Redis caching, WebSocket broadcasting, and auth.

**Scope:**
- OddsBlaze API polling loop (5-second cycle, ~20 sportsbooks)
- Redis cache for hot odds data
- WebSocket server (push updates to connected clients)
- REST API routes (auth, user preferences)
- Internal HTTP calls to Python service for fair value
- NextAuth.js integration (email/password + Google SSO)
- Rate limit management (250 calls/min OddsBlaze limit)
- Graceful degradation (stale data banners, Python service down handling)
- Docker containerization

**Dependencies:** Python Engine Agent (needs fair value API spec)

### 🔧 DevOps Agent
**Mission:** Set up project infrastructure — Docker Compose for local dev, DB migrations, Railway config.

**Scope:**
- `docker-compose.yml` — Node + Python + PostgreSQL + Redis
- Database migrations (users, user_preferences, sessions)
- `.env.example` with all required variables
- Railway deployment config (Procfiles, nixpacks)
- GitHub Actions CI (lint + test)

**Runs in parallel with Python Engine Agent (no dependency)**

## Phase 2: Product (Week 2)

### 🎨 Frontend Agent
**Mission:** Build the Next.js application with the odds table, auth UI, and vintage aesthetic.

**Scope:**
- TanStack Table with all columns (sportsbooks as sub-columns)
- WebSocket client with auto-reconnect
- +EV highlighting (color-coded by edge magnitude)
- Filter bar (Game, Player, Bet Type, Sportsbook, Min Edge %)
- Deep links (sportsbook cells → bet slip in new tab)
- Sticky left columns on mobile (Player, Bet Type, Line, Best Odds, Edge %)
- Kelly bet size column (client-side calculation from user profile)
- Auth pages (login, signup via NextAuth)
- Profile page (preferred sportsbooks, bankroll, Kelly fraction)
- Vintage sports card aesthetic (chrome/branding, not data cells)
- Landing page with blurred odds preview
- Legal footer on every page

**Dependencies:** Node Backend Agent (needs WebSocket + REST API spec)

## Phase 3: Polish & Launch (Week 3)

### All Agents collaborate on:
- Integration testing (end-to-end data flow)
- Error handling verification
- Railway deployment
- UptimeRobot + Sentry setup
- Google Analytics
- 21+ age gate
- How It Works page
- Legal pages (placeholder ToS, Privacy)

## Communication Protocol

1. **Moose Ops** receives sprint objectives from Bujar
2. **Moose Ops** breaks objectives into tasks and dispatches to worker agents
3. **Worker agents** report results back to Moose Ops
4. **Moose Ops** consolidates progress and reports to Bujar
5. **Bujar** reports broad updates + decision points to Kevin

## Key Decisions Made

- **No Stripe for MVP** — Free access to validate demand first
- **OddsBlaze as primary data source** (not TheOddsAPI from reference)
- **Desktop-first** — mobile is functional but not optimized
- **All sportsbooks visible by default** — user can customize in profile
- **Mode 1 fair value only for MVP** — Modes 2 & 3 are V2

## Repository

- **GitHub:** https://github.com/kevhox1/Bet-With-Moose
- **Branch strategy:** `main` (production), feature branches per agent
