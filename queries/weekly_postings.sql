-- New postings per week over the last 26 weeks, including empty weeks.
-- by_posted_date: first publication date reported by the API (works from day one).
-- by_first_seen:  first collector run that saw the posting (grows with daily runs).
WITH RECURSIVE
ref AS (
    SELECT date(MAX(date(started_at)), 'weekday 0', '-6 days') AS last_week FROM runs
),
weeks (week_start) AS (
    SELECT date(last_week, '-175 days') FROM ref          -- 25 weeks earlier
    UNION ALL
    SELECT date(week_start, '+7 days') FROM weeks, ref
    WHERE week_start < ref.last_week
),
scope AS (
    SELECT
        date(posted_date,     'weekday 0', '-6 days') AS posted_week,
        date(first_seen_date, 'weekday 0', '-6 days') AS seen_week
    FROM postings
    WHERE (:it_only = 0 OR role_category <> 'other')
)
SELECT
    w.week_start,
    (SELECT COUNT(*) FROM scope WHERE posted_week = w.week_start) AS by_posted_date,
    (SELECT COUNT(*) FROM scope WHERE seen_week   = w.week_start) AS by_first_seen
FROM weeks AS w
ORDER BY w.week_start;
