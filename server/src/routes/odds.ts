import { FastifyInstance } from 'fastify';
import { getCachedOddsSnapshot, getStaleFlag } from '../services/redis';
import { getCurrentSnapshot } from '../services/websocket';

export function registerOddsRoutes(app: FastifyInstance): void {
  // Get current odds snapshot (REST fallback for clients that don't use WebSocket)
  app.get('/api/odds', async (_request, reply) => {
    try {
      // Try Redis first, fall back to in-memory
      let data = await getCachedOddsSnapshot();
      if (!data) {
        data = getCurrentSnapshot();
      }

      const stale = await getStaleFlag();

      return reply.send({
        type: 'snapshot',
        timestamp: new Date().toISOString(),
        dataStale: stale,
        data: data ?? [],
      });
    } catch (err: any) {
      console.error('[Odds] Error fetching snapshot:', err?.message);
      return reply.status(500).send({ error: 'Internal server error' });
    }
  });

  // Health check
  app.get('/api/health', async (_request, reply) => {
    return reply.send({ status: 'ok', timestamp: new Date().toISOString() });
  });

  app.get('/health', async (_request, reply) => {
    return reply.send({ status: 'ok', timestamp: new Date().toISOString() });
  });
}
