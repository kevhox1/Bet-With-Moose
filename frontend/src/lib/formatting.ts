export function formatAmericanOdds(odds: number): string {
  if (odds > 0) return `+${odds}`;
  return `${odds}`;
}

export function formatEdge(edgePct: number): string {
  return `${edgePct >= 0 ? '+' : ''}${edgePct.toFixed(1)}%`;
}

export function formatMoney(amount: number): string {
  return `$${amount.toFixed(2)}`;
}

export function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ago`;
}
