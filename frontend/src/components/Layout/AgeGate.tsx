'use client';
import { useState, useEffect } from 'react';

export default function AgeGate() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (typeof window !== 'undefined' && !localStorage.getItem('ageVerified')) {
      setShow(true);
    }
  }, []);

  if (!show) return null;

  return (
    <div className="age-gate-overlay">
      <div className="age-gate-card">
        <h2>Age Verification</h2>
        <p>You must be 21 or older to use this site.</p>
        <div className="age-gate-buttons">
          <button
            className="btn btn-primary btn-lg"
            onClick={() => { localStorage.setItem('ageVerified', 'true'); setShow(false); }}
          >
            I am 21+
          </button>
          <button
            className="btn btn-outline btn-lg"
            onClick={() => { window.location.href = 'https://www.ncpgambling.org/'; }}
          >
            I am under 21
          </button>
        </div>
      </div>
    </div>
  );
}
