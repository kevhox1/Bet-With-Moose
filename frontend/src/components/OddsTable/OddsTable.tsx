'use client';
import { useMemo, useRef } from 'react';
import { useReactTable, getCoreRowModel, getSortedRowModel, flexRender, SortingState } from '@tanstack/react-table';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useState } from 'react';
import { OddsRow, KellyMultiplier } from '@/types/odds';
import { buildColumns } from './columns';
import { getEVRowClass } from './EVHighlight';

interface OddsTableProps {
  data: OddsRow[];
  visibleBooks: string[];
  bankroll: number | null;
  kellyMultiplier: KellyMultiplier;
}

export default function OddsTable({ data, visibleBooks, bankroll, kellyMultiplier }: OddsTableProps) {
  const [sorting, setSorting] = useState<SortingState>([{ id: 'edgePct', desc: true }]);
  const parentRef = useRef<HTMLDivElement>(null);

  const columns = useMemo(
    () => buildColumns({ visibleBooks, bankroll, kellyMultiplier }),
    [visibleBooks, bankroll, kellyMultiplier]
  );

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const { rows } = table.getRowModel();

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 36,
    overscan: 20,
  });

  if (data.length === 0) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
        <p style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>No +EV bets found</p>
        <p style={{ fontSize: '0.85rem' }}>Try adjusting your filters or check back later.</p>
      </div>
    );
  }

  return (
    <div className="odds-table-wrap" ref={parentRef} style={{ maxHeight: '75vh', overflow: 'auto' }}>
      <table className="odds-table">
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((header) => (
                <th
                  key={header.id}
                  style={{ width: header.getSize(), cursor: header.column.getCanSort() ? 'pointer' : 'default' }}
                  onClick={header.column.getToggleSortingHandler()}
                >
                  {flexRender(header.column.columnDef.header, header.getContext())}
                  {{ asc: ' ↑', desc: ' ↓' }[header.column.getIsSorted() as string] ?? ''}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody style={{ height: `${virtualizer.getTotalSize()}px`, position: 'relative' }}>
          {virtualizer.getVirtualItems().map((vi) => {
            const row = rows[vi.index];
            return (
              <tr
                key={row.id}
                className={getEVRowClass(row.original.edgePct)}
                style={{ height: vi.size }}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
      <div style={{ padding: '0.5rem 0.75rem', fontSize: '0.7rem', color: 'var(--text-muted)', borderTop: '1px solid var(--border-light)' }}>
        Showing {rows.length} {rows.length === 1 ? 'bet' : 'bets'}
      </div>
    </div>
  );
}
