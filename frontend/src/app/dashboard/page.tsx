'use client';
import { useState, useEffect, useMemo } from 'react';
import { useWebSocket, useOddsStore } from '@/hooks/useWebSocket';
import { useOddsData, useUniqueValues } from '@/hooks/useOddsData';
import { useAuthStore } from '@/hooks/useAuth';
import OddsTable from '@/components/OddsTable/OddsTable';
import FilterBar from '@/components/Filters/FilterBar';
import DataStaleWarning from '@/components/ui/DataStaleWarning';
import { ALL_SPORTSBOOKS } from '@/types/odds';

export default function DashboardPage() {
  const { init, preferences, isAuthenticated } = useAuthStore();
  useEffect(() => { init(); }, [init]);

  useWebSocket();

  const [filters, setFilters] = useState({
    game: '',
    player: '',
    market: '',
    minEdge: 0,
    showNegativeEV: false,
    selectedBooks: [] as string[],
  });

  const filteredData = useOddsData({
    game: filters.game || undefined,
    player: filters.player || undefined,
    market: filters.market || undefined,
    minEdge: filters.minEdge,
    showNegativeEV: filters.showNegativeEV,
  });

  const { games, markets, books } = useUniqueValues();

  const visibleBooks = useMemo(() => {
    if (filters.selectedBooks.length > 0) return filters.selectedBooks;
    if (books.length > 0) return books;
    return [...ALL_SPORTSBOOKS];
  }, [filters.selectedBooks, books]);

  const handleFilterChange = (partial: Partial<typeof filters>) => {
    setFilters((prev) => ({ ...prev, ...partial }));
  };

  return (
    <>
      <DataStaleWarning />
      <div className="page-container" style={{ paddingTop: '1rem', paddingBottom: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem' }}>
          <h2 style={{ fontFamily: 'var(--font-display)', color: 'var(--navy)' }}>
            🫎 +EV Player Props
          </h2>
          {!isAuthenticated && (
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Log in for personalized Kelly sizing
            </span>
          )}
        </div>

        <FilterBar
          filters={filters}
          onChange={handleFilterChange}
          games={games}
          markets={markets}
        />

        <OddsTable
          data={filteredData}
          visibleBooks={visibleBooks}
          bankroll={preferences.bankroll}
          kellyMultiplier={preferences.kellyFraction}
        />
      </div>
    </>
  );
}
