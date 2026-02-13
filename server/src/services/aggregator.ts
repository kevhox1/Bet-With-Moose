import {
  OddsBlazeResponse,
  AggregatedProp,
  BookOdds,
  OppositeOddsLookup,
} from '../types/odds';

/**
 * Parse American odds string/number to integer.
 */
function parsePrice(raw: string | number): number {
  const s = String(raw).trim();
  if (s.startsWith('+')) return parseInt(s.slice(1), 10);
  const n = parseInt(s, 10);
  return isNaN(n) ? 0 : n;
}

/**
 * Convert display market name to API-style key.
 * "Player Double Double" → "player_double_double"
 */
function marketToKey(market: string): string {
  return market.toLowerCase().replace(/\s+/g, '_').replace(/\+/g, '');
}

/**
 * Aggregate player props across all sportsbooks into a unified map.
 * Port of aggregate_player_props() from reference bot.
 */
export function aggregatePlayerProps(
  allOdds: Record<string, OddsBlazeResponse>,
): Map<string, AggregatedProp> {
  const props = new Map<string, AggregatedProp>();

  for (const [book, data] of Object.entries(allOdds)) {
    const bookLower = book.toLowerCase();

    for (const event of data.events ?? []) {
      // Skip live games
      if (event.live) continue;

      const away = event.teams?.away?.name ?? 'Away';
      const home = event.teams?.home?.name ?? 'Home';
      const game = `${away} @ ${home}`;

      for (const odd of event.odds ?? []) {
        const market = odd.market ?? '';
        if (!market.includes('Player') && !market.includes('First Basket')) continue;

        const selection = odd.selection ?? {};
        let playerName = selection.name ?? '';
        if (!playerName) {
          playerName = odd.player?.name ?? 'Unknown';
        }

        const line = selection.line != null ? Number(selection.line) : null;
        const side = selection.side ?? 'Over';

        // Build unified key
        const propKey = line != null
          ? `${playerName}|${market}|${side} ${line}`
          : `${playerName}|${market}|${side}`;

        const price = parsePrice(odd.price ?? '0');
        if (price === 0) continue;

        const link = odd.links?.desktop ?? '';

        const existing = props.get(propKey);
        if (existing) {
          existing.books[bookLower] = { price, link, main: odd.main, sgp: odd.sgp };
        } else {
          props.set(propKey, {
            player: playerName,
            market,
            marketKey: marketToKey(market),
            selection: { side, line },
            event: {
              id: event.id,
              game,
              gameDate: event.date ?? '',
              away,
              home,
            },
            books: {
              [bookLower]: { price, link, main: odd.main, sgp: odd.sgp },
            },
          });
        }
      }
    }
  }

  return props;
}

/**
 * Build opposite-side lookup for 2-way de-vig.
 * Port of build_opposite_lookup() from reference bot.
 */
export function buildOppositeLookup(
  props: Map<string, AggregatedProp>,
): OppositeOddsLookup {
  const lookup: OppositeOddsLookup = {};

  const opposites: Record<string, string> = {
    Over: 'Under', Under: 'Over', Yes: 'No', No: 'Yes',
  };

  for (const [propKey, propData] of props) {
    const parts = propKey.split('|');
    if (parts.length !== 3) continue;

    const [player, market, sideLine] = parts;
    const spaceIdx = sideLine.indexOf(' ');
    const side = spaceIdx >= 0 ? sideLine.slice(0, spaceIdx) : sideLine;
    const line = spaceIdx >= 0 ? sideLine.slice(spaceIdx + 1) : '';

    const oppSide = opposites[side];
    if (!oppSide) continue;

    const oppKey = line ? `${player}|${market}|${oppSide} ${line}` : `${player}|${market}|${oppSide}`;
    const oppProp = props.get(oppKey);
    if (oppProp) {
      lookup[propKey] = oppProp.books;
    }
  }

  return lookup;
}
