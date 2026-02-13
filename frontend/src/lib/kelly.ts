import { KellyMultiplier } from '@/types/odds';

export function calculateKellyBetSize(
  bankroll: number,
  kellyFraction: number,
  edgePct: number,
  kellyMultiplier: KellyMultiplier = 0.25
): number {
  if (bankroll <= 0 || edgePct <= 0 || kellyFraction <= 0) return 0;
  return Math.round(bankroll * kellyFraction * (edgePct / 100) * kellyMultiplier * 100) / 100;
}
