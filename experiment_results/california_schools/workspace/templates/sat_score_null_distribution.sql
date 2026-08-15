WITH score_distribution AS (
    SELECT
        cds,
        rtype,
        COUNT(*) AS total_records,
        COUNT(avgscrread IS NOT NULL) AS valid_read,
        COUNT(avgscrmath IS NOT NULL) AS valid_math,
        COUNT(avgscrwrite IS NOT NULL) AS valid_write,
        ROUND(CAST(COUNT(avgscrread IS NOT NULL) AS DOUBLE PRECISION) * 100.0 / COUNT(*)) AS read_pct,
        ROUND(CAST(COUNT(avgscrmath IS NOT NULL) AS DOUBLE PRECISION) * 100.0 / COUNT(*)) AS math_pct,
        ROUND(CAST(COUNT(avgscrwrite IS NOT NULL) AS DOUBLE PRECISION) * 100.0 / COUNT(*)) AS write_pct
    FROM satscores
    GROUP BY cds, rtype
)
SELECT * FROM score_distribution ORDER BY cds, rtype;
