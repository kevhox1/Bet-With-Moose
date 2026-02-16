/**
 * Rewrite sportsbook deep links based on user's state.
 *
 * State-dependent books:
 * - FanDuel: desktop = {state}.sportsbook.fanduel.com, mobile = sportsbook.fanduel.com (no state)
 * - BetRivers: {state}.betrivers.com
 * - BetMGM: sports.{state}.betmgm.com
 * - BallyBet: {state}.ballybet.com
 *
 * All others (DraftKings, Caesars, etc.) are state-independent.
 */

const STATE_PATTERNS: Record<string, {
  detect: string;
  rewrite: (link: string, state: string) => string;
}> = {
  fanduel: {
    detect: 'sportsbook.fanduel.com',
    rewrite: (link, state) => {
      // Extract path after domain
      const match = link.match(/sportsbook\.fanduel\.com(\/.*)?$/);
      const path = match?.[1] ?? '';
      return `https://${state}.sportsbook.fanduel.com${path}`;
    },
  },
  betrivers: {
    detect: 'betrivers.com',
    rewrite: (link, state) => {
      const match = link.match(/betrivers\.com(\/.*)?$/);
      const path = match?.[1] ?? '';
      return `https://${state}.betrivers.com${path}`;
    },
  },
  betmgm: {
    detect: 'betmgm.com',
    rewrite: (link, state) => {
      const match = link.match(/betmgm\.com(\/.*)?$/);
      const path = match?.[1] ?? '';
      return `https://sports.${state}.betmgm.com${path}`;
    },
  },
  'bally-bet': {
    detect: 'ballybet.com',
    rewrite: (link, state) => {
      const match = link.match(/ballybet\.com(\/.*)?$/);
      const path = match?.[1] ?? '';
      return `https://${state}.ballybet.com${path}`;
    },
  },
};

/**
 * Rewrite a single book link for the given state.
 * Returns the original link if no rewriting is needed.
 */
export function rewriteLink(link: string, bookKey: string, state: string): string {
  if (!link || !state) return link;

  // Check by book key first
  const pattern = STATE_PATTERNS[bookKey];
  if (pattern && link.includes(pattern.detect)) {
    return pattern.rewrite(link, state);
  }

  // Fallback: check all patterns by detect string
  for (const p of Object.values(STATE_PATTERNS)) {
    if (link.includes(p.detect)) {
      return p.rewrite(link, state);
    }
  }

  return link;
}

/**
 * Rewrite all book links in a books object.
 */
export function rewriteBookLinks(
  books: Record<string, { price: number; link: string }>,
  state: string,
): Record<string, { price: number; link: string }> {
  if (!state) return books;

  const result: Record<string, { price: number; link: string }> = {};
  for (const [book, data] of Object.entries(books)) {
    result[book] = {
      price: data.price,
      link: rewriteLink(data.link, book, state),
    };
  }
  return result;
}
