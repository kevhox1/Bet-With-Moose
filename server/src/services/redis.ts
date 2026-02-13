import Redis from 'ioredis';
import { config } from '../config/env';
import { OddsRow } from '../types/odds';

let redis: Redis | null = null;

export function getRedis(): Redis {
  if (!redis) {
    redis = new Redis(config.redisUrl, {
      maxRetriesPerRequest: 3,
      retryStrategy(times) {
        if (times > 10) return null;
        return Math.min(times * 200, 5000);
      },
      lazyConnect: true,
    });
    redis.on('error', (err) => console.error('[Redis] Connection error:', err.message));
  }
  return redis;
}

export async function connectRedis(): Promise<void> {
  const r = getRedis();
  try {
    await r.connect();
    console.log('[Redis] Connected');
  } catch (err: any) {
    if (err?.message?.includes('already')) {
      console.log('[Redis] Already connected');
    } else {
      console.error('[Redis] Failed to connect:', err?.message);
    }
  }
}

const ODDS_KEY = 'odds:current';
const STALE_KEY = 'odds:stale';
const TTL = 60;

export async function cacheOddsSnapshot(rows: OddsRow[]): Promise<void> {
  try {
    const r = getRedis();
    const pipeline = r.pipeline();
    pipeline.set(ODDS_KEY, JSON.stringify(rows), 'EX', TTL);
    await pipeline.exec();
  } catch (err: any) {
    console.error('[Redis] Failed to cache snapshot:', err?.message);
  }
}

export async function getCachedOddsSnapshot(): Promise<OddsRow[] | null> {
  try {
    const data = await getRedis().get(ODDS_KEY);
    return data ? JSON.parse(data) : null;
  } catch {
    return null;
  }
}

export async function setStaleFlag(stale: boolean): Promise<void> {
  try {
    await getRedis().set(STALE_KEY, stale ? '1' : '0', 'EX', TTL);
  } catch {}
}

export async function getStaleFlag(): Promise<boolean> {
  try {
    return (await getRedis().get(STALE_KEY)) === '1';
  } catch {
    return false;
  }
}

export async function updateBookTimestamp(book: string): Promise<void> {
  try {
    await getRedis().set(`odds:book:${book}:lastUpdate`, Date.now().toString(), 'EX', TTL);
  } catch {}
}

export async function disconnectRedis(): Promise<void> {
  if (redis) {
    await redis.quit().catch(() => {});
    redis = null;
  }
}
