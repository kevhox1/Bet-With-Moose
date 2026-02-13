import { Server as HttpServer } from 'http';
import { WebSocketServer, WebSocket } from 'ws';
import { OddsRow, SnapshotMessage } from '../types/odds';

let wss: WebSocketServer | null = null;
let currentSnapshot: OddsRow[] = [];
let currentStale = false;

export function initWebSocket(server: HttpServer): void {
  wss = new WebSocketServer({ server });

  wss.on('connection', (ws) => {
    console.log(`[WS] Client connected (total: ${wss!.clients.size})`);

    // Send current snapshot on connect
    const msg: SnapshotMessage = {
      type: 'snapshot',
      timestamp: new Date().toISOString(),
      dataStale: currentStale,
      data: currentSnapshot,
    };
    try {
      ws.send(JSON.stringify(msg));
    } catch {}

    ws.on('close', () => {
      console.log(`[WS] Client disconnected (total: ${wss!.clients.size})`);
    });

    ws.on('error', (err) => {
      console.error('[WS] Client error:', err.message);
    });
  });

  console.log('[WS] WebSocket server initialized');
}

export function broadcastSnapshot(rows: OddsRow[], dataStale: boolean): void {
  currentSnapshot = rows;
  currentStale = dataStale;

  if (!wss || wss.clients.size === 0) return;

  const msg: SnapshotMessage = {
    type: 'snapshot',
    timestamp: new Date().toISOString(),
    dataStale,
    data: rows,
  };
  const payload = JSON.stringify(msg);

  for (const client of wss.clients) {
    if (client.readyState === WebSocket.OPEN) {
      try {
        client.send(payload);
      } catch {}
    }
  }
}

export function getConnectedClients(): number {
  return wss?.clients.size ?? 0;
}

export function getCurrentSnapshot(): OddsRow[] {
  return currentSnapshot;
}

export function closeWebSocket(): void {
  if (wss) {
    for (const client of wss.clients) {
      client.close();
    }
    wss.close();
    wss = null;
  }
}
