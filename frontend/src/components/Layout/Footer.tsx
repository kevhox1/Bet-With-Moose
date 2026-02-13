import Link from 'next/link';

export default function Footer() {
  return (
    <footer className="footer">
      <div className="footer-inner">
        <p>
          <strong>Moose Bets</strong> is not a sportsbook. For informational and entertainment purposes only.
        </p>
        <p>
          Past performance does not guarantee future results. Must be 21+ to use this site.
        </p>
        <p>
          Please gamble responsibly. National Problem Gambling Helpline: <strong>1-800-GAMBLER</strong>
        </p>
        <p style={{ marginTop: '0.75rem' }}>
          <Link href="/terms">Terms of Service</Link> · <Link href="/privacy">Privacy Policy</Link> · <Link href="/how-it-works">How It Works</Link>
        </p>
      </div>
    </footer>
  );
}
