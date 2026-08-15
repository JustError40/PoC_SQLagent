WITH ranked_schools AS (
    SELECT
        s.sname,
        ROW_NUMBER() OVER (PARTITION BY s.cname ORDER BY s.avgscrread DESC) as rn
    FROM satscores s
    JOIN schools sch ON s.cds = sch.cdscode
    WHERE sch.virtual = 'Y'
)
SELECT sname
FROM ranked_schools
WHERE rn <= 5;
