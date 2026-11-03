-- Number of current postings per title-based role category.
SELECT role_category, COUNT(*) AS postings
FROM current_postings
GROUP BY role_category
ORDER BY postings DESC;
