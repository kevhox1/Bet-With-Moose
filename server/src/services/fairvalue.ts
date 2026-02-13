import { config } from '../config/env';
import {
  AggregatedProp,
  OppositeOddsLookup,
  FairValueRequest,
  FairValueResponse,
  FairValueResult,
} from '../types/odds';

/**
 * Call the Python fair value calculator service.
 * Returns results keyed by prop key, or null if service unavailable.
 */
export async function fetchFairValues(
  props: Map<string, AggregatedProp>,
  oppositeLookup: OppositeOddsLookup,
): Promise<Record<string, FairValueResult> | null> {
  if (props.size === 0) return {};

  const markets: FairValueRequest['markets'] = [];
  const keyMap: string[] = []; // index → propKey mapping

  for (const [propKey, prop] of props) {
    const bookOdds: Record<string, { price: number }> = {};
    for (const [book, data] of Object.entries(prop.books)) {
      bookOdds[book] = { price: data.price };
    }

    let oppositeOdds: Record<string, { price: number }> | undefined;
    const opp = oppositeLookup[propKey];
    if (opp) {
      oppositeOdds = {};
      for (const [book, data] of Object.entries(opp)) {
        oppositeOdds[book] = { price: data.price };
      }
    }

    markets.push({
      player: prop.player,
      market_key: prop.marketKey,
      line: prop.selection.line,
      side: prop.selection.side,
      book_odds: bookOdds,
      opposite_odds: oppositeOdds,
    });
    keyMap.push(propKey);
  }

  try {
    const url = `${config.calculatorServiceUrl}/v1/fair-value`;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);

    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ markets }),
      signal: controller.signal,
    });

    clearTimeout(timeout);

    if (!resp.ok) {
      console.error(`[FairValue] Service returned ${resp.status}`);
      return null;
    }

    const data = (await resp.json()) as FairValueResponse;
    return data.results ?? null;
  } catch (err: any) {
    if (err?.name === 'AbortError') {
      console.error('[FairValue] Request timed out');
    } else {
      console.error('[FairValue] Service unavailable:', err?.message);
    }
    return null;
  }
}
