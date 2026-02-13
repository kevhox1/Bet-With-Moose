export interface BookOdds {
  price: number;
  link: string;
}

export interface OddsRow {
  id: string;
  game: string;
  gameDate: string;
  player: string;
  market: string;
  marketKey: string;
  line: number | null;
  side: string;
  books: { [sportsbook: string]: BookOdds };
  bestBook: string;
  bestOdds: number;
  fairOdds: number | null;
  fairProbability: number | null;
  edgePct: number | null;
  kellyFraction: number | null;
  coverage: number;
  calcType: string;
  lastUpdated: string;
}

export interface SnapshotMessage {
  type: 'snapshot';
  timestamp: string;
  dataStale: boolean;
  data: OddsRow[];
}

export type WebSocketMessage = SnapshotMessage;

export type ConnectionStatus = 'connected' | 'connecting' | 'disconnected';

export type KellyMultiplier = 1 | 0.5 | 0.25 | 0.125;

export interface UserPreferences {
  preferredBooks: string[];
  bankroll: number | null;
  kellyFraction: KellyMultiplier;
  minEdge: number;
  showNegativeEV: boolean;
}

export const ALL_SPORTSBOOKS = [
  'DraftKings', 'FanDuel', 'BetMGM', 'Caesars', 'PointsBet',
  'BetRivers', 'Fanatics', 'ESPN BET', 'Hard Rock', 'bet365',
  'BetWay', 'Fliff', 'Underdog', 'PrizePicks', 'Sleeper', 'Betr'
] as const;

export type Sportsbook = typeof ALL_SPORTSBOOKS[number];
