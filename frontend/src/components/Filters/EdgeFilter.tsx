'use client';

interface Props {
  value: number;
  onChange: (v: number) => void;
}

export default function EdgeFilter({ value, onChange }: Props) {
  return (
    <div className="form-group" style={{ minWidth: 120 }}>
      <label className="form-label">Min Edge %</label>
      <input
        className="form-input"
        type="number"
        min={0}
        max={50}
        step={0.5}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
      />
    </div>
  );
}
