'use client';
import GameFilter from './GameFilter';
import PlayerFilter from './PlayerFilter';
import MarketFilter from './MarketFilter';
import BookFilter from './BookFilter';
import EdgeFilter from './EdgeFilter';

interface FilterState {
  game: string;
  player: string;
  market: string;
  minEdge: number;
  showNegativeEV: boolean;
  selectedBooks: string[];
}

interface Props {
  filters: FilterState;
  onChange: (f: Partial<FilterState>) => void;
  games: string[];
  markets: string[];
}

export default function FilterBar({ filters, onChange, games, markets }: Props) {
  return (
    <div className="filter-bar">
      <GameFilter games={games} value={filters.game} onChange={(game) => onChange({ game })} />
      <PlayerFilter value={filters.player} onChange={(player) => onChange({ player })} />
      <MarketFilter markets={markets} value={filters.market} onChange={(market) => onChange({ market })} />
      <BookFilter selected={filters.selectedBooks} onChange={(selectedBooks) => onChange({ selectedBooks })} />
      <EdgeFilter value={filters.minEdge} onChange={(minEdge) => onChange({ minEdge })} />
      <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', paddingTop: '1.25rem' }}>
        <input
          type="checkbox"
          id="showAll"
          checked={filters.showNegativeEV}
          onChange={(e) => onChange({ showNegativeEV: e.target.checked })}
          style={{ accentColor: 'var(--burgundy)' }}
        />
        <label htmlFor="showAll" style={{ fontSize: '0.8rem', cursor: 'pointer' }}>Show All</label>
      </div>
    </div>
  );
}
