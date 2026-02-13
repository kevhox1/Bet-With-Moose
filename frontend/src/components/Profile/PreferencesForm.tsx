'use client';
import { useState } from 'react';
import { useAuthStore } from '@/hooks/useAuth';
import { KellyMultiplier } from '@/types/odds';
import BookSelector from './BookSelector';

export default function PreferencesForm() {
  const { preferences, updatePreferences } = useAuthStore();
  const [prefs, setPrefs] = useState(preferences);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await updatePreferences(prefs);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch {} finally {
      setSaving(false);
    }
  };

  return (
    <div className="profile-page">
      <h1>Preferences</h1>
      <div className="card">
        <BookSelector
          selected={prefs.preferredBooks}
          onChange={(preferredBooks) => setPrefs({ ...prefs, preferredBooks })}
        />

        <div className="form-group">
          <label className="form-label">Bankroll ($)</label>
          <input
            className="form-input"
            type="number"
            min={0}
            placeholder="Enter your bankroll"
            value={prefs.bankroll ?? ''}
            onChange={(e) => setPrefs({ ...prefs, bankroll: e.target.value ? parseFloat(e.target.value) : null })}
          />
        </div>

        <div className="form-group">
          <label className="form-label">Kelly Fraction</label>
          <select
            className="form-input form-select"
            value={prefs.kellyFraction}
            onChange={(e) => setPrefs({ ...prefs, kellyFraction: parseFloat(e.target.value) as KellyMultiplier })}
          >
            <option value={1}>Full Kelly</option>
            <option value={0.5}>Half Kelly</option>
            <option value={0.25}>Quarter Kelly (recommended)</option>
            <option value={0.125}>Eighth Kelly</option>
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">Minimum Edge %</label>
          <input
            className="form-input"
            type="number"
            min={0}
            max={50}
            step={0.5}
            value={prefs.minEdge}
            onChange={(e) => setPrefs({ ...prefs, minEdge: parseFloat(e.target.value) || 0 })}
          />
        </div>

        <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <input
            type="checkbox"
            id="showNeg"
            checked={prefs.showNegativeEV}
            onChange={(e) => setPrefs({ ...prefs, showNegativeEV: e.target.checked })}
            style={{ accentColor: 'var(--burgundy)' }}
          />
          <label htmlFor="showNeg" style={{ cursor: 'pointer' }}>Show negative EV bets</label>
        </div>

        <button className="btn btn-primary" onClick={handleSave} disabled={saving} style={{ marginTop: '1rem' }}>
          {saving ? 'Saving...' : saved ? '✓ Saved!' : 'Save Preferences'}
        </button>
      </div>
    </div>
  );
}
