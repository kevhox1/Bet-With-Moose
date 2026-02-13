import { config } from '../config/env';
import {
  OddsBlazeResponse,
  OddsRow,
  SPORTSBOOKS,
  SHARP_BOOKS,
} from '../types/odds';
import { aggregatePlayerProps, buildOppositeLookup } from './aggregator';
import { fetchFairValues } from './fairvalue';
import { cacheOddsSnapshot, setStaleFlag, updateBookTimestamp } from './redis';
import { broadcastSnapshot } from './websocket';

// State
const bookData: Record<string, OddsBlazeResponse> = {};
let lastSuccessfulFetch = Date.now();
let pollTimer: ReturnType<typeof setInterval> | null = null;
let bookIndex = 0;

function isDataStale(): boolean {
  return Date.now() - lastSuccessfulFetch > config.stalenessThresholdMs;
}

/**
 * Fetch odds for a single sportsbook from OddsBlaze.
 */
async function fetchBook(sportsbook: string): Promise<OddsBlazeResponse | null> {
  try {
    const url = `${config.oddsblaze.baseUrl}?key=${config.oddsblaze.apiKey}&sportsbook=${sportsbook}&league=nba`;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);

    const resp = await fetch(url, { signal: controller.signal });
    clearTimeout(timeout);

    if (!resp.ok) {
      console.warn(`[OddsBlaze] ${sportsbook} returned ${resp.status}`);
      return null;
    }

    return (await resp.json()) as OddsBlazeResponse;
  } catch (err: any) {
    console.error(`[OddsBlaze] Error fetching ${sportsbook}:`, err?.message);
    return null;
  }
}

/**
 * Build OddsRow[] from aggregated props + fair value results.
 */
function buildOddsRows(
  props: Map<string, import('../types/odds').AggregatedProp>,
  fairValues: Record<string, import('../types/odds').FairValueResult> | null,
): OddsRow[] {
  const rows: OddsRow[] = [];
  const now = new Date().toISOString();

  for (const [propKey, prop] of props) {
    // Find best retail odds
    let bestBook = '';
    let bestOdds = -Infinity;
    const clientBooks: Record<string, { price: number; link: string }> = {};

    for (const [book, data] of Object.entries(prop.books)) {
      clientBooks[book] = { price: data.price, link: data.link };
      if (!SHARP_BOOKS.includes(book) && data.price > bestOdds) {
        bestOdds = data.price;
        bestBook = book;
      }
    }

    // Fallback if all books are sharp
    if (!bestBook) {
      for (const [book, data] of Object.entries(prop.books)) {
        if (data.price > bestOdds) {
          bestOdds = data.price;
          bestBook = book;
        }
      }
    }

    const fv = fairValues?.[propKey] ?? null;

    rows.push({
      id: propKey,
      game: prop.event.game,
      gameDate: prop.event.gameDate,
      player: prop.player,
      market: `${prop.market.replace('Player ', '')} ${prop.selection.side}`,
      marketKey: prop.marketKey,
      line: prop.selection.line,
      side: prop.selection.side,
      books: clientBooks,
      bestBook,
      bestOdds: bestOdds === -Infinity ? 0 : bestOdds,
      fairOdds: fv?.fair_odds ?? null,
      fairProbability: fv?.fair_probability ?? null,
      edgePct: fv?.edge_pct ?? null,
      kellyFraction: fv?.kelly_fraction ?? null,
      coverage: Object.keys(prop.books).length,
      calcType: fv?.calc_type ?? null,
      lastUpdated: now,
    });
  }

  return rows;
}

/**
 * Poll one sportsbook, then aggregate, compute fair values, cache, and broadcast.
 */
async function pollOnce(): Promise<void> {
  const book = SPORTSBOOKS[bookIndex % SPORTSBOOKS.length];
  bookIndex++;

  const data = await fetchBook(book);
  if (data && data.events) {
    bookData[book] = data;
    lastSuccessfulFetch = Date.now();
    updateBookTimestamp(book).catch(() => {});
    console.log(`[OddsBlaze] ${book}: ${data.events.length} events`);
  }

  // Aggregate all current book data
  const props = aggregatePlayerProps(bookData);
  const oppositeLookup = buildOppositeLookup(props);

  // Fetch fair values (non-blocking failure)
  const fairValues = await fetchFairValues(props, oppositeLookup);

  // Build rows
  const rows = buildOddsRows(props, fairValues);
  const stale = isDataStale();

  // Cache and broadcast
  await Promise.all([
    cacheOddsSnapshot(rows).catch(() => {}),
    setStaleFlag(stale).catch(() => {}),
  ]);

  broadcastSnapshot(rows, stale);
}

/**
 * Start the polling loop.
 */
export function startPolling(): void {
  if (pollTimer) return;
  console.log(`[OddsBlaze] Starting polling loop (${config.pollIntervalMs}ms interval)`);

  // First poll immediately
  pollOnce().catch((err) => console.error('[OddsBlaze] Poll error:', err?.message));

  pollTimer = setInterval(() => {
    pollOnce().catch((err) => console.error('[OddsBlaze] Poll error:', err?.message));
  }, config.pollIntervalMs);
}

/**
 * Stop the polling loop.
 */
export function stopPolling(): void {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
    console.log('[OddsBlaze] Polling stopped');
  }
}
