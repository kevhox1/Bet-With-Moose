export default function PrivacyPage() {
  return (
    <div className="page-container" style={{ maxWidth: 720, margin: '2rem auto', padding: '0 1.5rem' }}>
      <h1 style={{ color: 'var(--burgundy)', marginBottom: '1.5rem' }}>Privacy Policy</h1>
      <div className="card">
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.8 }}>
          Privacy policy content coming soon. Moose Bets collects minimal data: your email, preferences
          (preferred sportsbooks, bankroll, Kelly fraction), and usage analytics. We do not sell your data
          to third parties. We do not track your betting activity on sportsbook sites.
        </p>
      </div>
    </div>
  );
}
