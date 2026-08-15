SELECT "School Type", COUNT(*) AS school_count, AVG("Enrollment (K-12)") AS avg_enrollment FROM frpm GROUP BY "School Type" ORDER BY school_count DESC;
