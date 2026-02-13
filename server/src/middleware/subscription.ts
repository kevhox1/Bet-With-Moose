import { FastifyRequest, FastifyReply } from 'fastify';

/**
 * Subscription/paywall middleware — dormant for MVP.
 * During free launch period, all authenticated users have full access.
 */
export async function subscriptionMiddleware(
  _request: FastifyRequest,
  _reply: FastifyReply,
): Promise<void> {
  // MVP: no paywall — all authenticated users pass through
  return;
}
