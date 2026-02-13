'use client';
import { useMemo } from 'react';
import { useOddsStore } from './useWebSocket';
import { OddsRow } from '@/types/odds';

interface FilterOptions {
  game?: string;
  player?: string;
  market?: string;
  minEdge: number;
  showNegativeEV: boolean;
  selectedBooks?: string[];
}

export function useOddsData(filters: FilterOptions) {
  const rows = useOddsStore((s) => s.rows);

  return useMemo(() => {
    let filtered = rows;

    if (!filters.showNegativeEV) {
      filtered = filtered.filter((r) => r.edgePct > 0);
    }

    if (filters.minEdge > 0) {
      filtered = filtered.filter((r) => r.edgePct >= filters.minEdge);
    }

    if (filters.game) {
      filtered = filtered.filter((r) => r.game === filters.game);
    }

    if (filters.player) {
      const q = filters.player.toLowerCase();
      filtered = filtered.filter((r) => r.player.toLowerCase().includes(q));
    }

    if (filters.market) {
      filtered = filtered.filter((r) => r.market === filters.market);
    }

    return filtered;
  }, [rows, filters]);
}

export function useUniqueValues() {
  const rows = useOddsStore((s) => s.rows);
  return useMemo(() => ({
    games: [...new Set(rows.map((r) => r.game))].sort(),
    players: [...new Set(rows.map((r) => r.player))].sort(),
    markets: [...new Set(rows.map((r) => r.market))].sort(),
    books: [...new Set(rows.flatMap((r) => Object.keys(r.books)))].sort(),
  }), [rows]);
}
