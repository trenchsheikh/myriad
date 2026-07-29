-- Myriad DuckDB schema
-- Source of truth: prd.md section 5
--
-- crowd_snapshots and predictions are APPEND ONLY.
-- Never UPDATE or DELETE rows in those tables.

CREATE TABLE IF NOT EXISTS matches (
  match_id      VARCHAR PRIMARY KEY,
  season        VARCHAR,
  match_date    DATE,
  kickoff_utc   TIMESTAMP,
  home_team_id  VARCHAR,
  away_team_id  VARCHAR,
  home_goals    INTEGER,
  away_goals    INTEGER,
  home_xg       DOUBLE,
  away_xg       DOUBLE,
  referee       VARCHAR,
  odds_open_h   DOUBLE,
  odds_open_d   DOUBLE,
  odds_open_a   DOUBLE,
  odds_close_h  DOUBLE,
  odds_close_d  DOUBLE,
  odds_close_a  DOUBLE,
  crowd_present BOOLEAN   -- False for COVID empty-stadium matches
);

-- Raw football-data.co.uk rows before team-name normalisation (Day 5).
CREATE TABLE IF NOT EXISTS matches_staging (
  season          VARCHAR,
  season_code     VARCHAR,
  match_date      DATE,
  home_team_raw   VARCHAR,
  away_team_raw   VARCHAR,
  home_goals      INTEGER,
  away_goals      INTEGER,
  referee         VARCHAR,
  odds_open_h     DOUBLE,
  odds_open_d     DOUBLE,
  odds_open_a     DOUBLE,
  odds_close_h    DOUBLE,
  odds_close_d    DOUBLE,
  odds_close_a    DOUBLE
);

-- APPEND ONLY. One row per player per capture hour.
CREATE TABLE IF NOT EXISTS crowd_snapshots (
  captured_at        TIMESTAMP,
  player_id          INTEGER,
  team_id            VARCHAR,
  position           VARCHAR,
  price              INTEGER,
  ownership_pct      DOUBLE,
  transfers_in_ev    INTEGER,
  transfers_out_ev   INTEGER,
  play_chance_pct    INTEGER,
  news               VARCHAR,
  news_added         TIMESTAMP
);

-- APPEND ONLY, NEVER UPDATED. Public scorecard credibility depends on this.
CREATE TABLE IF NOT EXISTS predictions (
  prediction_id   VARCHAR PRIMARY KEY,
  created_at      TIMESTAMP,
  model_version   VARCHAR,
  model_variant   VARCHAR,       -- 'base' | 'crowd' | 'live'
  match_id        VARCHAR,
  p_home          DOUBLE,
  p_draw          DOUBLE,
  p_away          DOUBLE,
  p_btts          DOUBLE,
  p_over25        DOUBLE,
  is_locked       BOOLEAN,
  git_sha         VARCHAR
);

CREATE TABLE IF NOT EXISTS teams (
  team_id VARCHAR PRIMARY KEY,
  canonical_name VARCHAR,
  stadium_lat DOUBLE,
  stadium_lon DOUBLE
);

CREATE TABLE IF NOT EXISTS team_aliases (
  alias VARCHAR,
  source VARCHAR,
  team_id VARCHAR
);

-- 2026-27 (and future) FPL fixture list, canonical team ids.
CREATE TABLE IF NOT EXISTS fixtures (
  fixture_id    INTEGER,
  season        VARCHAR,
  gameweek      INTEGER,
  kickoff_utc   TIMESTAMP,
  home_team_id  VARCHAR,
  away_team_id  VARCHAR,
  finished      BOOLEAN,
  fpl_code      INTEGER
);

-- Speeds up gap checks and "already loaded?" lookups.
CREATE INDEX IF NOT EXISTS idx_crowd_captured_at
  ON crowd_snapshots (captured_at);

CREATE INDEX IF NOT EXISTS idx_crowd_player_captured
  ON crowd_snapshots (player_id, captured_at);

CREATE INDEX IF NOT EXISTS idx_fixtures_season_gw
  ON fixtures (season, gameweek);
