'use client';
import { useUniqueValues } from '@/hooks/useOddsData';

/** Map API book keys to friendly display names */
const BOOK_DISPLAY: Record<string, string> = {
  'draftkings': 'DraftKings',
  'fanduel': 'FanDuel',
  'fanduel-yourway': 'FanDuel YourWay',
  'betmgm': 'BetMGM',
  'caesars': 'Caesars',
  'betrivers': 'BetRivers',
  'bet365': 'bet365',
  'fliff': 'Fliff',
  'bally-bet': 'Bally Bet',
  'betparx': 'BetParx',
  'thescore': 'theScore',
  'hard-rock': 'Hard Rock',
  'espnbet': 'ESPN BET',
  'fanatics': 'Fanatics',
};

function displayName(key: string): string {
  return BOOK_DISPLAY[key] || key;
}

interface Props {
  selected: string[];
  onChange: (books: string[]) => void;
}

export default function BookFilter({ selected, onChange }: Props) {
  const { books } = useUniqueValues();

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
          {books.map((book) => (
            <label key={book} className="book-check" style={{ padding: '0.2rem 0' }}>
              <input type="checkbox" checked={selected.includes(book)} onChange={() => toggle(book)} />
              {' '}{displayName(book)}
            </label>
          ))}
        </div>
      </details>
    </div>
  );
}
