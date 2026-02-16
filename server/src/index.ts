import Fastify from 'fastify';
import cors from '@fastify/cors';
import rateLimit from '@fastify/rate-limit';
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
  await app.register(rateLimit, {
    global: false, // only apply where specified
  });

  // PostgreSQL
  const db = new Pool({ connectionString: config.databaseUrl });
  db.on('error', (err) => console.error('[PG] Pool error:', err.message));

  // Test DB connection & run migrations
  try {
    await db.query('SELECT 1');
    console.log('[PG] Connected');

    // Auto-create tables if they don't exist
    await db.query(`
      CREATE TABLE IF NOT EXISTS users (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        email VARCHAR(255) UNIQUE NOT NULL,
        name VARCHAR(255),
        password_hash VARCHAR(255),
        google_id VARCHAR(255),
        subscription_status VARCHAR(50) DEFAULT 'free',
        stripe_customer_id VARCHAR(255),
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
      );
      CREATE TABLE IF NOT EXISTS user_preferences (
        user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        preferred_sportsbooks TEXT[] DEFAULT '{}',
        bankroll DECIMAL(12,2),
        kelly_fraction DECIMAL(4,3) DEFAULT 0.250,
        min_edge DECIMAL(5,3) DEFAULT 0.000,
        min_coverage INTEGER DEFAULT 3,
        display_mode VARCHAR(50) DEFAULT 'default',
        show_negative_ev BOOLEAN DEFAULT false,
        updated_at TIMESTAMPTZ DEFAULT NOW()
      );
      CREATE TABLE IF NOT EXISTS sessions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
        session_token VARCHAR(255) UNIQUE NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW()
      );
    `);
    console.log('[PG] Migrations complete');
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
