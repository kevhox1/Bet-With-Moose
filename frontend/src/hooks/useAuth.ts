'use client';
import { create } from 'zustand';
import { api } from '@/lib/api';
import { UserPreferences, KellyMultiplier } from '@/types/odds';

interface AuthState {
  token: string | null;
  user: { name: string; email: string } | null;
  preferences: UserPreferences;
  isAuthenticated: boolean;
  init: () => void;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  updatePreferences: (prefs: Partial<UserPreferences>) => Promise<void>;
}

const defaultPrefs: UserPreferences = {
  preferredBooks: [],
  bankroll: null,
  kellyFraction: 0.25 as KellyMultiplier,
  minEdge: 0,
  showNegativeEV: false,
  state: 'ny',
};

export const useAuthStore = create<AuthState>((set, get) => ({
  token: null,
  user: null,
  preferences: defaultPrefs,
  isAuthenticated: false,

  init: () => {
    if (typeof window === 'undefined') return;
    const token = localStorage.getItem('token');
    const user = localStorage.getItem('user');
    if (token && user) {
      set({ token, user: JSON.parse(user), isAuthenticated: true });
      api.getPreferences().then((prefs) => set({ preferences: { ...defaultPrefs, ...prefs } })).catch(() => {});
    }
  },

  login: async (email, password) => {
    const { token, user } = await api.login(email, password);
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(user));
    set({ token, user, isAuthenticated: true });
  },

  register: async (name, email, password) => {
    const { token, user } = await api.register(name, email, password);
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(user));
    set({ token, user, isAuthenticated: true });
  },

  logout: () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    set({ token: null, user: null, isAuthenticated: false, preferences: defaultPrefs });
  },

  updatePreferences: async (prefs) => {
    const merged = { ...get().preferences, ...prefs };
    await api.updatePreferences(merged);
    set({ preferences: merged });
  },
}));
