'use client';
import { useEffect, useRef, useCallback } from 'react';
import { create } from 'zustand';
import { OddsRow, ConnectionStatus, WebSocketMessage } from '@/types/odds';

interface OddsState {
  rows: OddsRow[];
  connectionStatus: ConnectionStatus;
  dataStale: boolean;
  lastUpdated: string | null;
  setRows: (rows: OddsRow[]) => void;
  setConnectionStatus: (s: ConnectionStatus) => void;
  setDataStale: (stale: boolean) => void;
  setLastUpdated: (ts: string) => void;
}

export const useOddsStore = create<OddsState>((set) => ({
  rows: [],
  connectionStatus: 'disconnected',
  dataStale: false,
  lastUpdated: null,
  setRows: (rows) => set({ rows }),
  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),
  setDataStale: (dataStale) => set({ dataStale }),
  setLastUpdated: (lastUpdated) => set({ lastUpdated }),
}));

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>();
  const attemptRef = useRef(0);
  const staleTimerRef = useRef<NodeJS.Timeout>();
  const { setRows, setConnectionStatus, setDataStale, setLastUpdated } = useOddsStore();

  const resetStaleTimer = useCallback(() => {
    if (staleTimerRef.current) clearTimeout(staleTimerRef.current);
    staleTimerRef.current = setTimeout(() => setDataStale(true), 30000);
  }, [setDataStale]);

  const connect = useCallback(() => {
    const url = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:3001';
    setConnectionStatus('connecting');
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnectionStatus('connected');
      attemptRef.current = 0;
      resetStaleTimer();
    };

    ws.onmessage = (event) => {
      try {
        const msg: WebSocketMessage = JSON.parse(event.data);
        if (msg.type === 'snapshot') {
          setRows(msg.data);
          setDataStale(msg.dataStale);
          setLastUpdated(msg.timestamp);
          resetStaleTimer();
        }
      } catch {}
    };

    ws.onclose = () => {
      setConnectionStatus('disconnected');
      const delay = Math.min(1000 * Math.pow(2, attemptRef.current), 30000);
      attemptRef.current++;
      reconnectTimeoutRef.current = setTimeout(connect, delay);
    };

    ws.onerror = () => ws.close();
  }, [setRows, setConnectionStatus, setDataStale, setLastUpdated, resetStaleTimer]);

  useEffect(() => {
    connect();
    return () => {
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (staleTimerRef.current) clearTimeout(staleTimerRef.current);
    };
  }, [connect]);
}
