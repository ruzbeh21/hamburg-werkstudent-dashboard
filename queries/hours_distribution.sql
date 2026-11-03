-- Stated weekly hours (upper value of a range, e.g. "16-20 h" counts as 20).
SELECT
    hours_max  AS hours,
    COUNT(*)   AS postings
FROM current_postings
WHERE hours_max IS NOT NULL
  AND (:it_only = 0 OR role_category <> 'other')
GROUP BY hours_max
ORDER BY hours_max;
