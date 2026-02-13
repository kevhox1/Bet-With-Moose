// =============================================================================
// OddsBlaze API Response Types
// =============================================================================

export interface OddsBlazeResponse {
  events: OddsBlazeEvent[];
}

export interface OddsBlazeEvent {
  id: string;
  teams: {
    away: { name: string };
    home: { name: string };
  };
  date: string;
  live: boolean;
  odds: OddsBlazeOdd[];
}

export interface OddsBlazeOdd {
  market: string;
  selection: {
    name?: string;
    line?: number | string;
    side?: string;
  };
  player?: { name: string };
  price: string | number;
  main?: boolean;
  sgp?: string;
  links?: {
    desktop?: string;
    mobile?: string;
  };
}

// =============================================================================
// Aggregated Internal Types
// =============================================================================

export interface BookOdds {
  price: number;
  link: string;
  main?: boolean;
  sgp?: string;
}

export interface AggregatedProp {
  player: string;
  market: string;
  marketKey: string;
  selection: {
    side: string;
    line: number | null;
  };
  event: {
    id: string;
    game: string;
    gameDate: string;
    away: string;
    home: string;
  };
  books: Record<string, BookOdds>;
}

export interface OppositeOddsLookup {
  [propKey: string]: Record<string, BookOdds>;
}

// =============================================================================
// Fair Value Types
// =============================================================================

export interface FairValueRequest {
  markets: FairValueMarket[];
}

export interface FairValueMarket {
  player: string;
  market_key: string;
  line: number | null;
  side: string;
  book_odds: Record<string, { price: number }>;
  opposite_odds?: Record<string, { price: number }>;
}

export interface FairValueResult {
  fair_probability: number;
  fair_odds: number;
  edge_pct: number;
  kelly_fraction: number;
  calc_type: string;
  best_book: string;
  best_odds: number;
  coverage: number;
  confidence_multiplier: number;
}

export interface FairValueResponse {
  results: Record<string, FairValueResult>;
}

// =============================================================================
// WebSocket / Client Types
// =============================================================================

export interface OddsRow {
  id: string;
  game: string;
  gameDate: string;
  player: string;
  market: string;
  marketKey: string;
  line: number | null;
  side: string;
  books: Record<string, { price: number; link: string }>;
  bestBook: string;
  bestOdds: number;
  fairOdds: number | null;
  fairProbability: number | null;
  edgePct: number | null;
  kellyFraction: number | null;
  coverage: number;
  calcType: string | null;
  lastUpdated: string;
}

export interface SnapshotMessage {
  type: 'snapshot';
  timestamp: string;
  dataStale: boolean;
  data: OddsRow[];
}

// =============================================================================
// User Types
// =============================================================================

export interface UserPreferences {
  preferred_sportsbooks: string[];
  bankroll: number;
  kelly_fraction: number;
  min_edge: number;
  min_coverage: number;
  display_mode: string;
}

export interface User {
  id: number;
  email: string;
  password_hash: string;
  created_at: Date;
  subscription_status: string;
}

// =============================================================================
// Constants
// =============================================================================

export const SPORTSBOOKS = [
  'draftkings', 'fanduel', 'fanduel-yourway', 'betmgm', 'caesars', 'betrivers',
  'fanatics', 'betparx', 'fliff', 'thescore', 'pinnacle', 'circa',
  'bet365', 'bally-bet', 'hard-rock', 'prophetx',
] as const;

export type Sportsbook = typeof SPORTSBOOKS[number];

export const SHARP_BOOKS: string[] = ['pinnacle', 'circa'];

export const BOOK_ABBREV: Record<string, string> = {
  draftkings: 'DK', fanduel: 'FD', 'fanduel-yourway': 'FDYW', betmgm: 'MG',
  caesars: 'CZ', betrivers: 'BR', fanatics: 'FN', betparx: 'BP', fliff: 'FL',
  thescore: 'TS', pinnacle: 'PN', circa: 'CI', bet365: 'B3', 'bally-bet': 'BB',
  'hard-rock': 'HR', prophetx: 'PX',
};
