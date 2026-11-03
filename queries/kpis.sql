-- Headline numbers for the KPI tiles.
-- "Current" = still online in the latest run. Time windows are relative to the
-- latest run date, not to "now", so results are reproducible.
-- :it_only = 1 restricts to data, software and IT-ops roles.
WITH ref AS (
    SELECT MAX(date(started_at)) AS run_date FROM runs
),
scope AS (
    SELECT * FROM current_postings
    WHERE (:it_only = 0 OR role_category <> 'other')
),
skill_share AS (
    SELECT ps.skill_id, COUNT(*) AS n
    FROM scope
    JOIN posting_skills AS ps USING (posting_id)
    WHERE ps.skill_id IN ('python', 'sql', 'power_bi')
    GROUP BY ps.skill_id
)
SELECT
    (SELECT run_date FROM ref)                                          AS run_date,
    (SELECT COUNT(*) FROM scope)                                        AS current_postings,
    (SELECT COUNT(*) FROM scope, ref
      WHERE posted_date > date(ref.run_date, '-7 days'))                AS posted_last_7_days,
    (SELECT COUNT(*) FROM scope, ref
      WHERE posted_date > date(ref.run_date, '-30 days'))               AS posted_last_30_days,
    (SELECT COUNT(DISTINCT company) FROM scope)                         AS companies,
    ROUND(100.0 * COALESCE((SELECT n FROM skill_share WHERE skill_id = 'python'), 0)
          / NULLIF((SELECT COUNT(*) FROM scope), 0), 1)                 AS python_pct,
    ROUND(100.0 * COALESCE((SELECT n FROM skill_share WHERE skill_id = 'sql'), 0)
          / NULLIF((SELECT COUNT(*) FROM scope), 0), 1)                 AS sql_pct,
    ROUND(100.0 * COALESCE((SELECT n FROM skill_share WHERE skill_id = 'power_bi'), 0)
          / NULLIF((SELECT COUNT(*) FROM scope), 0), 1)                 AS power_bi_pct,
    ROUND(100.0 * (SELECT COUNT(*) FROM scope WHERE work_mode IN ('remote', 'hybrid'))
          / NULLIF((SELECT COUNT(*) FROM scope), 0), 1)                 AS remote_hybrid_pct,
    ROUND(100.0 * (SELECT COUNT(*) FROM scope WHERE hours_max IS NOT NULL)
          / NULLIF((SELECT COUNT(*) FROM scope), 0), 1)                 AS hours_stated_pct,
    -- share whose full text was analysed (skills/hours/languages need it)
    ROUND(100.0 * (SELECT COUNT(*) FROM scope WHERE has_details = 1)
          / NULLIF((SELECT COUNT(*) FROM scope), 0), 1)                 AS details_pct;
