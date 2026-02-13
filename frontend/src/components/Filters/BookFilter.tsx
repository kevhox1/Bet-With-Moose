'use client';
import { ALL_SPORTSBOOKS } from '@/types/odds';

interface Props {
  selected: string[];
  onChange: (books: string[]) => void;
}

export default function BookFilter({ selected, onChange }: Props) {
  const toggle = (book: string) => {
    if (selected.includes(book)) onChange(selected.filter((b) => b !== book));
    else onChange([...selected, book]);
  };

  return (
    <div className="form-group" style={{ minWidth: 200 }}>
      <label className="form-label">Sportsbooks</label>
      <details style={{ position: 'relative' }}>
        <summary className="form-input" style={{ cursor: 'pointer', listStyle: 'none' }}>
          {selected.length === 0 ? 'All Books' : `${selected.length} selected`}
        </summary>
        <div style={{
          position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 10,
          background: 'white', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
          padding: '0.5rem', maxHeight: 240, overflow: 'auto', boxShadow: 'var(--shadow-md)',
        }}>
          {ALL_SPORTSBOOKS.map((book) => (
            <label key={book} className="book-check" style={{ padding: '0.2rem 0' }}>
              <input type="checkbox" checked={selected.includes(book)} onChange={() => toggle(book)} />
              {book}
            </label>
          ))}
        </div>
      </details>
    </div>
  );
}
