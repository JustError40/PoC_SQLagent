SELECT COUNT(*) as total_records, AVG("Enrollment (K-12)") as avg_enrollment FROM frpm WHERE "Enrollment (K-12)" IS NOT NULL;
