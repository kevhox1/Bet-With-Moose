export default function HowItWorksPage() {
  return (
    <div className="page-container" style={{ maxWidth: 720, margin: '2rem auto', padding: '0 1.5rem' }}>
      <h1 style={{ color: 'var(--burgundy)', marginBottom: '1.5rem' }}>How It Works</h1>
      <div className="card">
        <h3 style={{ color: 'var(--navy)', marginBottom: '0.75rem' }}>1. We Collect Odds</h3>
        <p style={{ marginBottom: '1.5rem', color: 'var(--text-secondary)' }}>
          Moose Bets pulls real-time NBA player prop odds from 16 major sportsbooks every few seconds.
        </p>

        <h3 style={{ color: 'var(--navy)', marginBottom: '0.75rem' }}>2. We Calculate Fair Value</h3>
        <p style={{ marginBottom: '1.5rem', color: 'var(--text-secondary)' }}>
          Using the power method (removing vig proportionally), we estimate the true probability of each outcome. When a sportsbook offers odds better than our fair value, that&apos;s a positive expected value (+EV) bet.
        </p>

        <h3 style={{ color: 'var(--navy)', marginBottom: '0.75rem' }}>3. We Size Your Bets</h3>
        <p style={{ marginBottom: '1.5rem', color: 'var(--text-secondary)' }}>
          The Kelly Criterion tells you exactly how much to wager based on your edge and bankroll. We default to Quarter Kelly for safety — you can customize this in your profile.
        </p>

        <h3 style={{ color: 'var(--navy)', marginBottom: '0.75rem' }}>4. You Place the Bet</h3>
        <p style={{ color: 'var(--text-secondary)' }}>
          Click any odds cell to go directly to that sportsbook (opens in a new tab). We never hold your money — Moose Bets is an information tool, not a sportsbook.
        </p>
      </div>
    </div>
  );
}
