import Link from 'next/link';

const PREVIEW_ROWS = [
  { player: 'LeBron James', bet: 'Points Over', line: '25.5', best: '+105', edge: '+3.2%' },
  { player: 'Stephen Curry', bet: 'Threes Over', line: '4.5', best: '+120', edge: '+5.1%' },
  { player: 'Nikola Jokić', bet: 'Assists Over', line: '8.5', best: '-105', edge: '+2.8%' },
  { player: 'Jayson Tatum', bet: 'Rebounds Over', line: '8.5', best: '+110', edge: '+1.4%' },
  { player: 'Luka Dončić', bet: 'Points Over', line: '28.5', best: '-110', edge: '+4.7%' },
  { player: 'Anthony Edwards', bet: 'Points Over', line: '24.5', best: '+100', edge: '+2.1%' },
];

export default function Home() {
  return (
    <>
      <section className="hero">
        <div className="page-container">
          <p style={{ fontSize: '3.5rem', marginBottom: '0.5rem' }}>🫎</p>
          <h1>Moose Bets</h1>
          <p className="subtitle">
            Real-time NBA player props odds with customizable fair value. Find +EV bets faster.
          </p>
          <Link href="/signup" className="btn btn-gold btn-lg" style={{ textDecoration: 'none' }}>
            Get Started — It&apos;s Free
          </Link>
        </div>
      </section>

      <div className="page-container">
        <section style={{ padding: '2.5rem 0' }}>
          <h2 style={{ textAlign: 'center', color: 'var(--navy)', marginBottom: '1.5rem' }}>
            Live Odds Preview
          </h2>
          <div className="blurred-preview">
            <div className="odds-table-wrap">
              <table className="odds-table">
                <thead>
                  <tr>
                    <th>Player</th><th>Bet Type</th><th>Line</th>
                    <th>DraftKings</th><th>FanDuel</th><th>BetMGM</th>
                    <th>Best Odds</th><th>Fair Value</th><th>Edge %</th>
                  </tr>
                </thead>
                <tbody>
                  {PREVIEW_ROWS.map((r, i) => (
                    <tr key={i} className={parseFloat(r.edge) >= 5 ? 'ev-row-5' : parseFloat(r.edge) >= 2 ? 'ev-row-2' : 'ev-row-0'}>
                      <td>{r.player}</td><td>{r.bet}</td><td>{r.line}</td>
                      <td className="odds-cell">-110</td><td className="odds-cell">-108</td><td className="odds-cell">{r.best}</td>
                      <td className="odds-cell best">{r.best}</td><td className="odds-cell">-115</td>
                      <td><span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--forest)' }}>{r.edge}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <p style={{ textAlign: 'center', marginTop: '1rem', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            Sign up to see full odds, fair values, and deep links →
          </p>
        </section>

        <section className="features">
          <div className="feature-card">
            <h3>⚡ Real-Time Odds</h3>
            <p>Live odds from 16 sportsbooks streamed via WebSocket. Never stale.</p>
          </div>
          <div className="feature-card">
            <h3>🎯 +EV Detection</h3>
            <p>Proprietary fair value calculation highlights positive expected value bets.</p>
          </div>
          <div className="feature-card">
            <h3>📊 Kelly Sizing</h3>
            <p>Customizable Kelly criterion bet sizing based on your bankroll and risk tolerance.</p>
          </div>
          <div className="feature-card">
            <h3>🔗 Deep Links</h3>
            <p>One click to place your bet directly on any sportsbook. Opens in a new tab.</p>
          </div>
        </section>
      </div>
    </>
  );
}
