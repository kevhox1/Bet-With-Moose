export function americanToImpliedProbability(odds: number): number {
  if (odds > 0) return 100 / (odds + 100);
  return Math.abs(odds) / (Math.abs(odds) + 100);
}

export function impliedProbabilityToAmerican(prob: number): number {
  if (prob <= 0 || prob >= 1) return 0;
  if (prob >= 0.5) return Math.round(-prob / (1 - prob) * 100);
  return Math.round((1 - prob) / prob * 100);
}

export function calculateEdge(fairProb: number, bookOdds: number): number {
  const impliedProb = americanToImpliedProbability(bookOdds);
  if (impliedProb <= 0) return 0;
  return ((fairProb - impliedProb) / impliedProb) * 100;
}
