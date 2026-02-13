import dotenv from 'dotenv';
import path from 'path';

dotenv.config({ path: path.resolve(__dirname, '../../.env') });

export const config = {
  port: parseInt(process.env.PORT || '3001', 10),
  oddsblaze: {
    apiKey: process.env.ODDSBLAZE_API_KEY || '',
    baseUrl: process.env.ODDSBLAZE_BASE_URL || 'https://odds.oddsblaze.com/',
  },
  calculatorServiceUrl: process.env.CALCULATOR_SERVICE_URL || 'http://localhost:8001',
  databaseUrl: process.env.DATABASE_URL || 'postgresql://moosebets:moosebets@localhost:5432/moosebets',
  redisUrl: process.env.REDIS_URL || 'redis://localhost:6379',
  jwtSecret: process.env.JWT_SECRET || 'dev-secret-change-in-production',
  pollIntervalMs: 5000,
  stalenessThresholdMs: 30000,
} as const;
