'use client';

interface Props {
  games: string[];
  value: string;
  onChange: (v: string) => void;
}

export default function GameFilter({ games, value, onChange }: Props) {
  return (
    <div className="form-group">
      <label className="form-label">Game</label>
      <select className="form-input form-select" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">All Games</option>
        {games.map((g) => <option key={g} value={g}>{g}</option>)}
      </select>
    </div>
  );
}
