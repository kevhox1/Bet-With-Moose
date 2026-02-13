import { FastifyInstance } from 'fastify';
import bcrypt from 'bcryptjs';
import { Pool } from 'pg';
import { signToken, authMiddleware } from '../middleware/auth';

export function registerAuthRoutes(app: FastifyInstance, db: Pool): void {
  // Register
  app.post<{ Body: { email: string; password: string } }>(
    '/api/auth/register',
    async (request, reply) => {
      try {
        const { email, password } = request.body ?? {};
        if (!email || !password) {
          return reply.status(400).send({ error: 'Email and password are required' });
        }
        if (password.length < 8) {
          return reply.status(400).send({ error: 'Password must be at least 8 characters' });
        }

        // Check existing
        const existing = await db.query('SELECT id FROM users WHERE email = $1', [email.toLowerCase()]);
        if (existing.rows.length > 0) {
          return reply.status(409).send({ error: 'Email already registered' });
        }

        const hash = await bcrypt.hash(password, 12);
        const result = await db.query(
          'INSERT INTO users (email, password_hash, subscription_status) VALUES ($1, $2, $3) RETURNING id',
          [email.toLowerCase(), hash, 'free'],
        );

        const userId = result.rows[0].id;
        const token = signToken({ userId, email: email.toLowerCase() });

        // Create default preferences
        await db.query(
          'INSERT INTO user_preferences (user_id) VALUES ($1) ON CONFLICT DO NOTHING',
          [userId],
        );

        return reply.status(201).send({ token, userId });
      } catch (err: any) {
        console.error('[Auth] Register error:', err?.message);
        return reply.status(500).send({ error: 'Internal server error' });
      }
    },
  );

  // Login
  app.post<{ Body: { email: string; password: string } }>(
    '/api/auth/login',
    async (request, reply) => {
      try {
        const { email, password } = request.body ?? {};
        if (!email || !password) {
          return reply.status(400).send({ error: 'Email and password are required' });
        }

        const result = await db.query(
          'SELECT id, email, password_hash FROM users WHERE email = $1',
          [email.toLowerCase()],
        );
        if (result.rows.length === 0) {
          return reply.status(401).send({ error: 'Invalid credentials' });
        }

        const user = result.rows[0];
        const valid = await bcrypt.compare(password, user.password_hash);
        if (!valid) {
          return reply.status(401).send({ error: 'Invalid credentials' });
        }

        const token = signToken({ userId: user.id, email: user.email });
        return reply.send({ token, userId: user.id });
      } catch (err: any) {
        console.error('[Auth] Login error:', err?.message);
        return reply.status(500).send({ error: 'Internal server error' });
      }
    },
  );

  // Session validation
  app.get(
    '/api/auth/session',
    { preHandler: authMiddleware },
    async (request, reply) => {
      try {
        const { userId, email } = request.user!;
        const result = await db.query(
          'SELECT id, email, subscription_status, created_at FROM users WHERE id = $1',
          [userId],
        );
        if (result.rows.length === 0) {
          return reply.status(404).send({ error: 'User not found' });
        }
        const user = result.rows[0];
        return reply.send({
          userId: user.id,
          email: user.email,
          subscriptionStatus: user.subscription_status,
          createdAt: user.created_at,
        });
      } catch (err: any) {
        console.error('[Auth] Session error:', err?.message);
        return reply.status(500).send({ error: 'Internal server error' });
      }
    },
  );
}
