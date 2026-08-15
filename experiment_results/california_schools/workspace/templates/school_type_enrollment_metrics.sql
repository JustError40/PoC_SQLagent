WITH school_type_stats AS (SELECT "School Type", COUNT(*) as school_count, AVG("Enrollment (K-12)") as avg_enrollment FROM frpm GROUP BY "School Type") SELECT * FROM school_type_stats LIMIT 10;
