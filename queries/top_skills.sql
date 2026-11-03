-- Top 15 requested skills among current postings (languages are shown separately).
WITH scope AS (
    SELECT * FROM current_postings
    WHERE (:it_only = 0 OR role_category <> 'other')
)
SELECT
    s.skill_id,
    s.label,
    s.category,
    COUNT(*)                                                    AS postings,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM scope), 1)   AS share_pct
FROM scope
JOIN posting_skills AS ps USING (posting_id)
JOIN skills         AS s  USING (skill_id)
WHERE s.category <> 'language'
GROUP BY s.skill_id, s.label, s.category
ORDER BY postings DESC, s.label
LIMIT 15;
