CREATE TABLE user_preferences (
  user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  preferred_sportsbooks TEXT[] DEFAULT '{}',
  bankroll DECIMAL(12,2),
  kelly_fraction DECIMAL(4,3) DEFAULT 0.250,
  min_edge_threshold DECIMAL(5,3) DEFAULT 0.000,
  show_negative_ev BOOLEAN DEFAULT false,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
