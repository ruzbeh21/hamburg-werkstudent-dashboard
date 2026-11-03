-- Required German and English level among current postings.
WITH scope AS (
    SELECT * FROM current_postings
    WHERE (:it_only = 0 OR role_category <> 'other')
)
SELECT 'german' AS language, COALESCE(german_level, 'not_mentioned') AS level, COUNT(*) AS postings
FROM scope GROUP BY 2
UNION ALL
SELECT 'english', COALESCE(english_level, 'not_mentioned'), COUNT(*)
FROM scope GROUP BY 2
ORDER BY language, postings DESC;
