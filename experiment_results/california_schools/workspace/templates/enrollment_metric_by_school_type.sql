SELECT "School Type", COUNT(*) as school_count, AVG("Enrollment (K-12)") as avg_k12 FROM frpm GROUP BY "School Type" ORDER BY school_count DESC LIMIT 10;
