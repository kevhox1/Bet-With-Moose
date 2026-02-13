'use client';
import { ALL_SPORTSBOOKS } from '@/types/odds';

interface Props {
  selected: string[];
  onChange: (books: string[]) => void;
}

export default function BookSelector({ selected, onChange }: Props) {
  const toggle = (book: string) => {
    if (selected.includes(book)) onChange(selected.filter((b) => b !== book));
    else onChange([...selected, book]);
  };

  return (
    <div className="form-group">
      <label className="form-label">Preferred Sportsbooks</label>
      <div className="book-grid">
        {ALL_SPORTSBOOKS.map((book) => (
          <label key={book} className="book-check">
            <input type="checkbox" checked={selected.includes(book)} onChange={() => toggle(book)} />
            {book}
          </label>
        ))}
      </div>
    </div>
  );
}
