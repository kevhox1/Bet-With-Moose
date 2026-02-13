import { FastifyInstance } from 'fastify';
import bcrypt from 'bcryptjs';
import { Pool } from 'pg';
import { signToken, authMiddleware } from '../middleware/auth';

export function registerAuthRoutes(app: FastifyInstance, db: Pool): void {
  // Register
  app.post<{ Body: { name?: string; email: string; password: string } }>(
    '/api/auth/register',
    async (request, reply) => {
      try {
        const { name, email, password } = request.body ?? {};
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
          'INSERT INTO users (email, name, password_hash, subscription_status) VALUES ($1, $2, $3, $4) RETURNING id, email, name',
          [email.toLowerCase(), name || null, hash, 'free'],
        );

        const row = result.rows[0];
        const userId = row.id;
        const token = signToken({ userId, email: email.toLowerCase() });

        // Create default preferences
        await db.query(
          'INSERT INTO user_preferences (user_id) VALUES ($1) ON CONFLICT DO NOTHING',
          [userId],
        );

        return reply.status(201).send({ token, user: { name: row.name || '', email: row.email } });
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
          'SELECT id, email, name, password_hash FROM users WHERE email = $1',
          [email.toLowerCase()],
        );
        if (result.rows.length === 0) {
          return reply.status(401).send({ error: 'Invalid credentials' });
        }

        const row = result.rows[0];
        const valid = await bcrypt.compare(password, row.password_hash);
        if (!valid) {
          return reply.status(401).send({ error: 'Invalid credentials' });
        }

        const token = signToken({ userId: row.id, email: row.email });
        return reply.send({ token, user: { name: row.name || '', email: row.email } });
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
