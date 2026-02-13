import Fastify from 'fastify';
import cors from '@fastify/cors';
import { Pool } from 'pg';
import { config } from './config/env';
import { connectRedis, disconnectRedis } from './services/redis';
import { initWebSocket, closeWebSocket } from './services/websocket';
import { startPolling, stopPolling } from './services/oddsblaze';
import { registerAuthRoutes } from './routes/auth';
import { registerUserRoutes } from './routes/user';
import { registerOddsRoutes } from './routes/odds';

async function main(): Promise<void> {
  // Fastify
  const app = Fastify({ logger: false });
  await app.register(cors, { origin: true });

  // PostgreSQL
  const db = new Pool({ connectionString: config.databaseUrl });
  db.on('error', (err) => console.error('[PG] Pool error:', err.message));

  // Test DB connection
  try {
    await db.query('SELECT 1');
    console.log('[PG] Connected');
  } catch (err: any) {
    console.warn('[PG] Not available (auth routes will fail):', err?.message);
  }

  // Redis
  await connectRedis();

  // Routes
  registerAuthRoutes(app, db);
  registerUserRoutes(app, db);
  registerOddsRoutes(app);

  // Start Fastify
  await app.listen({ port: config.port, host: '0.0.0.0' });
  console.log(`[Server] Listening on port ${config.port}`);

  // WebSocket on same server
  const httpServer = app.server;
  initWebSocket(httpServer);

  // Start OddsBlaze polling
  startPolling();

  // Graceful shutdown
  const shutdown = async (signal: string) => {
    console.log(`[Server] ${signal} received, shutting down...`);
    stopPolling();
    closeWebSocket();
    await app.close();
    await db.end();
    await disconnectRedis();
    process.exit(0);
  };

  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));
}

main().catch((err) => {
  console.error('[Server] Fatal error:', err);
  process.exit(1);
});
