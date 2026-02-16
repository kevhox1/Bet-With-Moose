import { ColumnDef } from '@tanstack/react-table';
import { OddsRow } from '@/types/odds';
import { formatAmericanOdds, timeAgo } from '@/lib/formatting';
import { calculateKellyBetSize } from '@/lib/kelly';
import { rewriteLink } from '@/lib/stateLinks';
import { KellyMultiplier } from '@/types/odds';
import EVHighlight from './EVHighlight';
import Link from 'next/link';

interface ColumnOptions {
  visibleBooks: string[];
  bankroll: number | null;
  kellyMultiplier: KellyMultiplier;
  state?: string;
  selectedBooks?: string[];
}

/** Calculate EV% for a specific book's price given the fair probability */
function calcBookEdge(bookPrice: number, fairProb: number | null): number | null {
  if (!fairProb || fairProb <= 0 || fairProb >= 1) return null;
  const impliedProb = bookPrice > 0
    ? 100 / (bookPrice + 100)
    : Math.abs(bookPrice) / (Math.abs(bookPrice) + 100);
  return ((fairProb - impliedProb) / impliedProb) * 100;
  // Simpler: edge = (1/impliedProb - 1/fairProb) ... but let's use the standard formula
}

function calcBookEdgeSimple(bookPrice: number, fairProb: number | null): number | null {
  if (!fairProb || fairProb <= 0 || fairProb >= 1) return null;
  // Decimal odds from american
  const decimal = bookPrice > 0 ? (bookPrice / 100) + 1 : (100 / Math.abs(bookPrice)) + 1;
  // EV% = (decimal * fairProb - 1) * 100
  return (decimal * fairProb - 1) * 100;
}

export function buildColumns({ visibleBooks, bankroll, kellyMultiplier, state, selectedBooks }: ColumnOptions): ColumnDef<OddsRow, unknown>[] {
  const base: ColumnDef<OddsRow, unknown>[] = [
    { accessorKey: 'game', header: 'Game', size: 140 },
    {
      id: 'gameDate',
      header: 'Date',
      size: 80,
      accessorFn: (row) => row.gameDate,
      cell: ({ getValue }) => {
        const v = getValue() as string | null;
        if (!v) return '—';
        const d = new Date(v);
        const date = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        const time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
        return `${date} ${time}`;
      },
    },
    { accessorKey: 'player', header: 'Player', size: 130 },
    {
      id: 'betType',
      header: 'Bet Type',
      size: 140,
      accessorFn: (row) => `${row.market} ${row.side}`,
    },
    {
      accessorKey: 'line',
      header: 'Line',
      size: 60,
      cell: ({ getValue }) => {
        const v = getValue() as number | null;
        return v !== null ? (v > 0 ? `O ${v}` : `U ${Math.abs(v)}`) : '—';
      },
    },
  ];

  const bookCols: ColumnDef<OddsRow, unknown>[] = visibleBooks.map((book) => ({
    id: `book_${book}`,
    header: book.length > 10 ? book.slice(0, 8) + '…' : book,
    size: 80,
    cell: ({ row }) => {
      const bookData = row.original.books[book];
      if (!bookData) return <span style={{ color: 'var(--text-muted)' }}>—</span>;
      const isBest = row.original.bestBook === book;
      return (
        <span className={`odds-cell ${isBest ? 'best' : ''}`}>
          <a href={state ? rewriteLink(bookData.link, book, state) : bookData.link} target="_blank" rel="noopener noreferrer">
            {formatAmericanOdds(bookData.price)}
          </a>
        </span>
      );
    },
  }));

  const tail: ColumnDef<OddsRow, unknown>[] = [
    {
      id: 'bestOdds',
      header: 'Best Odds',
      size: 110,
      cell: ({ row }) => {
        const r = row.original;
        const bestBookData = r.books[r.bestBook];
        const link = bestBookData
          ? (state ? rewriteLink(bestBookData.link, r.bestBook, state) : bestBookData.link)
          : '';
        return (
          <span className="odds-cell best">
            {link ? (
              <a href={link} target="_blank" rel="noopener noreferrer">
                {r.bestBook} {formatAmericanOdds(r.bestOdds)}
              </a>
            ) : (
              <>{r.bestBook} {formatAmericanOdds(r.bestOdds)}</>
            )}
          </span>
        );
      },
    },
    {
      accessorKey: 'fairOdds',
      header: 'Fair Value',
      size: 80,
      cell: ({ getValue }) => (
        <span className="odds-cell">{formatAmericanOdds(getValue() as number)}</span>
      ),
    },
    {
      accessorKey: 'edgePct',
      header: 'Edge %',
      size: 75,
      cell: ({ getValue }) => <EVHighlight edgePct={getValue() as number} />,
    },
    {
      id: 'kellyBet',
      header: 'Kelly Bet',
      size: 90,
      cell: ({ row }) => {
        if (!bankroll) {
          return <Link href="/profile" style={{ fontSize: '0.75rem' }}>Set bankroll →</Link>;
        }
        const amount = calculateKellyBetSize(bankroll, row.original.kellyFraction ?? 0, row.original.edgePct ?? 0, kellyMultiplier);
        if (amount <= 0) return <span style={{ color: 'var(--text-muted)' }}>—</span>;
        return <span className="odds-cell">${amount.toFixed(0)}</span>;
      },
    },
    {
      accessorKey: 'lastUpdated',
      header: 'Updated',
      size: 75,
      cell: ({ getValue }) => (
        <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
          {timeAgo(getValue() as string)}
        </span>
      ),
    },
  ];

  // Add "Your EV" column when specific books are selected
  const yourEvCol: ColumnDef<OddsRow, unknown>[] = (selectedBooks && selectedBooks.length > 0) ? [{
    id: 'yourEdge',
    header: 'Your EV %',
    size: 80,
    cell: ({ row }) => {
      const r = row.original;
      // Find the best price among selected books
      let bestPrice = -Infinity;
      for (const book of selectedBooks!) {
        const data = r.books[book];
        if (data && data.price !== 0 && data.price > bestPrice) {
          bestPrice = data.price;
        }
      }
      if (bestPrice === -Infinity) return <span style={{ color: 'var(--text-muted)' }}>—</span>;
      const ev = calcBookEdgeSimple(bestPrice, r.fairProbability);
      if (ev === null) return <span style={{ color: 'var(--text-muted)' }}>—</span>;
      return <EVHighlight edgePct={parseFloat(ev.toFixed(2))} />;
    },
  }] : [];

  return [...base, ...bookCols, ...yourEvCol, ...tail];
}
