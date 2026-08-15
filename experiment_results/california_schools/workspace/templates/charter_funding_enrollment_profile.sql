WITH join_data AS (
    SELECT
        frpm.cdscode,
        frpm."Enrollment (K-12)",
        schools.charter,
        schools.fundingtype
    FROM frpm
    JOIN schools ON frpm.cdscode = schools.cdscode
    LIMIT 10000
)
SELECT
    charter AS charter_status,
    fundingtype,
    COUNT(*) AS school_count,
    AVG("Enrollment (K-12)") AS avg_enrollment
FROM join_data
GROUP BY charter, fundingtype
LIMIT 100;
