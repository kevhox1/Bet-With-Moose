import { FastifyInstance } from 'fastify';
import { Pool } from 'pg';
import { authMiddleware } from '../middleware/auth';

export function registerUserRoutes(app: FastifyInstance, db: Pool): void {
  // Get profile
  app.get(
    '/api/user/profile',
    { preHandler: authMiddleware },
    async (request, reply) => {
      try {
        const result = await db.query(
          'SELECT id, email, subscription_status, created_at FROM users WHERE id = $1',
          [request.user!.userId],
        );
        if (result.rows.length === 0) {
          return reply.status(404).send({ error: 'User not found' });
        }
        return reply.send(result.rows[0]);
      } catch (err: any) {
        console.error('[User] Profile error:', err?.message);
        return reply.status(500).send({ error: 'Internal server error' });
      }
    },
  );

  // Get preferences
  app.get(
    '/api/user/preferences',
    { preHandler: authMiddleware },
    async (request, reply) => {
      try {
        const result = await db.query(
          'SELECT * FROM user_preferences WHERE user_id = $1',
          [request.user!.userId],
        );
        if (result.rows.length === 0) {
          return reply.send({
            preferred_sportsbooks: [],
            bankroll: 1000,
            kelly_fraction: 0.25,
            min_edge: 5,
            min_coverage: 3,
            display_mode: 'default',
          });
        }
        return reply.send(result.rows[0]);
      } catch (err: any) {
        console.error('[User] Preferences error:', err?.message);
        return reply.status(500).send({ error: 'Internal server error' });
      }
    },
  );

  // Update preferences
  app.put<{
    Body: {
      preferred_sportsbooks?: string[];
      bankroll?: number;
      kelly_fraction?: number;
      min_edge?: number;
      min_coverage?: number;
      display_mode?: string;
    };
  }>(
    '/api/user/preferences',
    { preHandler: authMiddleware },
    async (request, reply) => {
      try {
        const {
          preferred_sportsbooks,
          bankroll,
          kelly_fraction,
          min_edge,
          min_coverage,
          display_mode,
        } = request.body ?? {};

        await db.query(
          `INSERT INTO user_preferences (user_id, preferred_sportsbooks, bankroll, kelly_fraction, min_edge, min_coverage, display_mode)
           VALUES ($1, $2, $3, $4, $5, $6, $7)
           ON CONFLICT (user_id) DO UPDATE SET
             preferred_sportsbooks = COALESCE($2, user_preferences.preferred_sportsbooks),
             bankroll = COALESCE($3, user_preferences.bankroll),
             kelly_fraction = COALESCE($4, user_preferences.kelly_fraction),
             min_edge = COALESCE($5, user_preferences.min_edge),
             min_coverage = COALESCE($6, user_preferences.min_coverage),
             display_mode = COALESCE($7, user_preferences.display_mode),
             updated_at = NOW()`,
          [
            request.user!.userId,
            preferred_sportsbooks ? JSON.stringify(preferred_sportsbooks) : null,
            bankroll ?? null,
            kelly_fraction ?? null,
            min_edge ?? null,
            min_coverage ?? null,
            display_mode ?? null,
          ],
        );

        return reply.send({ success: true });
      } catch (err: any) {
        console.error('[User] Update preferences error:', err?.message);
        return reply.status(500).send({ error: 'Internal server error' });
      }
    },
  );
}
