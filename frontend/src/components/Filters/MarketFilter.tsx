'use client';

interface Props {
  markets: string[];
  value: string;
  onChange: (v: string) => void;
}

export default function MarketFilter({ markets, value, onChange }: Props) {
  return (
    <div className="form-group">
      <label className="form-label">Bet Type</label>
      <select className="form-input form-select" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">All Types</option>
        {markets.map((m) => <option key={m} value={m}>{m}</option>)}
      </select>
    </div>
  );
}
