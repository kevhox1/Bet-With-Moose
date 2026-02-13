'use client';

interface Props {
  value: string;
  onChange: (v: string) => void;
}

export default function PlayerFilter({ value, onChange }: Props) {
  return (
    <div className="form-group">
      <label className="form-label">Player</label>
      <input
        className="form-input"
        type="text"
        placeholder="Search player..."
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
