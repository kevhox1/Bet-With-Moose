'use client';
import { useOddsStore } from '@/hooks/useWebSocket';
import { timeAgo } from '@/lib/formatting';

export default function DataStaleWarning() {
  const { dataStale, lastUpdated, connectionStatus } = useOddsStore();

  if (connectionStatus === 'connecting' || connectionStatus === 'disconnected') {
    return <div className="reconnecting-bar">🔄 {connectionStatus === 'connecting' ? 'Connecting...' : 'Reconnecting...'}</div>;
  }

  if (!dataStale) return null;

  return (
    <div className="stale-banner">
      ⚠️ Data may be delayed {lastUpdated ? `— last updated ${timeAgo(lastUpdated)}` : ''}
    </div>
  );
}
