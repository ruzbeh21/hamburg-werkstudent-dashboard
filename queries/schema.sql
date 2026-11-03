-- Schema for the Hamburg working-student job market database (SQLite).
-- Applied by src/db.py; safe to run repeatedly.

PRAGMA foreign_keys = ON;

-- One row per collector run (from data/raw/search/<run>/manifest.json).
CREATE TABLE IF NOT EXISTS runs (
    run_id            TEXT PRIMARY KEY,          -- e.g. 2026-11-03T184618Z
    started_at        TEXT NOT NULL,             -- ISO timestamp, UTC
    finished_at       TEXT,
    location          TEXT,
    radius_km         INTEGER,
    unique_postings   INTEGER,
    details_fetched   INTEGER,
    postings_per_term TEXT                       -- JSON object {term: count}
);

-- One row per logical job posting. Re-posts of the same job (new reference
-- number, same normalised title + company) update the existing row.
CREATE TABLE IF NOT EXISTS postings (
    posting_id      INTEGER PRIMARY KEY,
    dedup_key       TEXT NOT NULL UNIQUE,        -- normalised title | company
    refnr           TEXT NOT NULL,               -- latest BA reference number
    title           TEXT NOT NULL,
    company         TEXT NOT NULL,
    city            TEXT,
    postcode        TEXT,
    district        TEXT,
    posted_date     TEXT,                        -- first publication (earliest version)
    first_seen_date TEXT NOT NULL,               -- first run that saw it
    last_seen_date  TEXT NOT NULL,               -- latest run that saw it
    offer_type      TEXT,
    working_time    TEXT,
    contract        TEXT,
    hours_min       INTEGER CHECK (hours_min IS NULL OR hours_min BETWEEN 1 AND 40),
    hours_max       INTEGER CHECK (hours_max IS NULL OR hours_max BETWEEN 1 AND 40),
    work_mode       TEXT NOT NULL CHECK (work_mode IN ('remote', 'hybrid', 'not_stated')),
    role_category   TEXT NOT NULL CHECK (role_category IN ('data', 'software', 'it_ops', 'other')),
    german_level    TEXT,                        -- C2, C1, B2, B1, mentioned or NULL
    english_level   TEXT,
    n_versions      INTEGER NOT NULL DEFAULT 1,
    source_url      TEXT NOT NULL,
    description     TEXT                         -- scrubbed of contact data; never exported
);

CREATE TABLE IF NOT EXISTS skills (
    skill_id TEXT PRIMARY KEY,
    label    TEXT NOT NULL,
    category TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posting_skills (
    posting_id INTEGER NOT NULL REFERENCES postings (posting_id) ON DELETE CASCADE,
    skill_id   TEXT    NOT NULL REFERENCES skills (skill_id) ON DELETE CASCADE,
    matched_in TEXT    NOT NULL CHECK (matched_in IN ('title', 'description')),
    PRIMARY KEY (posting_id, skill_id)
);

CREATE INDEX IF NOT EXISTS idx_postings_posted_date ON postings (posted_date);
CREATE INDEX IF NOT EXISTS idx_postings_last_seen   ON postings (last_seen_date);
CREATE INDEX IF NOT EXISTS idx_postings_company     ON postings (company);
CREATE INDEX IF NOT EXISTS idx_postings_role        ON postings (role_category);
CREATE INDEX IF NOT EXISTS idx_posting_skills_skill ON posting_skills (skill_id);

-- Postings that were still online in the most recent run.
CREATE VIEW IF NOT EXISTS current_postings AS
SELECT p.*
FROM postings AS p
WHERE p.last_seen_date = (SELECT MAX(date(started_at)) FROM runs);
