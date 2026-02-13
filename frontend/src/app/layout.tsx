import type { Metadata } from 'next';
import './globals.css';
import Header from '@/components/Layout/Header';
import Footer from '@/components/Layout/Footer';
import AgeGate from '@/components/Layout/AgeGate';

export const metadata: Metadata = {
  title: 'Moose Bets — Real-Time NBA Player Props Odds',
  description: 'Find +EV NBA player prop bets with real-time odds comparison, customizable fair value, and Kelly criterion bet sizing.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AgeGate />
        <Header />
        <main style={{ minHeight: 'calc(100vh - 200px)' }}>{children}</main>
        <Footer />
      </body>
    </html>
  );
}
