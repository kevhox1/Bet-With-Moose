CREATE TABLE user_preferences (
  user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  preferred_sportsbooks TEXT[] DEFAULT '{}',
  bankroll DECIMAL(12,2),
  kelly_fraction DECIMAL(4,3) DEFAULT 0.250,
  min_edge DECIMAL(5,3) DEFAULT 0.000,
  min_coverage INTEGER DEFAULT 3,
  display_mode VARCHAR(50) DEFAULT 'default',
  show_negative_ev BOOLEAN DEFAULT false,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
