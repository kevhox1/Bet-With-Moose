const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3001';

async function request(path: string, options: RequestInit = {}) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: res.statusText }));
    throw new Error(err.message || 'Request failed');
  }
  return res.json();
}

export const api = {
  login: (email: string, password: string) =>
    request('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  register: (name: string, email: string, password: string) =>
    request('/api/auth/register', { method: 'POST', body: JSON.stringify({ name, email, password }) }),
  getPreferences: async () => {
    const raw = await request('/api/user/preferences');
    // Convert snake_case from server to camelCase for frontend
    return {
      preferredBooks: raw.preferred_sportsbooks ?? [],
      bankroll: raw.bankroll ?? null,
      kellyFraction: raw.kelly_fraction ?? 0.25,
      minEdge: raw.min_edge ?? 0,
      showNegativeEV: raw.show_negative_ev ?? false,
    };
  },
  updatePreferences: (prefs: Record<string, unknown>) =>
    request('/api/user/preferences', {
      method: 'PUT',
      body: JSON.stringify({
        preferred_sportsbooks: prefs.preferredBooks,
        bankroll: prefs.bankroll,
        kelly_fraction: prefs.kellyFraction,
        min_edge: prefs.minEdge,
        show_negative_ev: prefs.showNegativeEV,
      }),
    }),
};
