-- Companies with the most current postings.
SELECT
    company,
    COUNT(*)                         AS postings,
    SUM(role_category <> 'other')    AS it_postings
FROM current_postings
WHERE (:it_only = 0 OR role_category <> 'other')
GROUP BY company
ORDER BY postings DESC, company
LIMIT 15;
