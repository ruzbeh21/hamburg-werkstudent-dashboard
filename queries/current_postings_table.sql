-- Rows for the searchable table on the dashboard. No description text is exported.
SELECT
    p.posting_id,
    p.title,
    p.company,
    p.district,
    p.posted_date,
    p.role_category,
    p.work_mode,
    p.hours_max,
    p.german_level,
    p.source_url,
    (SELECT GROUP_CONCAT(label, ', ')
       FROM (SELECT s.label
               FROM posting_skills AS ps
               JOIN skills AS s USING (skill_id)
              WHERE ps.posting_id = p.posting_id
                AND s.category <> 'language'
              ORDER BY s.label))                 AS skills
FROM current_postings AS p
ORDER BY p.posted_date DESC, p.title;
