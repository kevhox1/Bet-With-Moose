'use client';
import Link from 'next/link';
import { useAuthStore } from '@/hooks/useAuth';
import { useOddsStore } from '@/hooks/useWebSocket';

export default function Header() {
  const { isAuthenticated, logout } = useAuthStore();
  const connectionStatus = useOddsStore((s) => s.connectionStatus);

  return (
    <header className="header">
      <div className="header-inner">
        <Link href="/" className="header-logo" style={{ textDecoration: 'none' }}>
          <span>🫎</span> Moose Bets
        </Link>
        <nav className="header-nav">
          {isAuthenticated ? (
            <>
              <Link href="/dashboard">Dashboard</Link>
              <Link href="/profile">Profile</Link>
              <Link href="/how-it-works">How It Works</Link>
              {connectionStatus === 'connected' && (
                <span style={{ fontSize: '0.7rem', color: '#7CBF7C' }}>● Live</span>
              )}
              <button onClick={logout} className="btn btn-sm btn-outline" style={{ color: 'white', borderColor: 'rgba(255,255,255,0.3)' }}>
                Log Out
              </button>
            </>
          ) : (
            <>
              <Link href="/how-it-works">How It Works</Link>
              <Link href="/login">Log In</Link>
              <Link href="/signup" className="btn btn-sm btn-gold" style={{ textDecoration: 'none' }}>
                Sign Up
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
