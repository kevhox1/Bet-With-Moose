export function getEVRowClass(edgePct: number): string {
  if (edgePct < 0) return 'ev-row-neg';
  if (edgePct >= 5) return 'ev-row-5';
  if (edgePct >= 2) return 'ev-row-2';
  if (edgePct > 0) return 'ev-row-0';
  return '';
}

interface EVHighlightProps {
  edgePct: number;
}

export default function EVHighlight({ edgePct }: EVHighlightProps) {
  const color = edgePct >= 5 ? 'var(--forest)' : edgePct >= 2 ? '#8B7A2E' : edgePct > 0 ? 'var(--text-primary)' : 'var(--negative-text)';
  return (
    <span style={{ fontWeight: edgePct >= 2 ? 700 : 400, color, fontFamily: 'var(--font-mono)' }}>
      {edgePct >= 0 ? '+' : ''}{edgePct.toFixed(1)}%
    </span>
  );
}
