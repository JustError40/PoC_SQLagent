SELECT fundingtype, COUNT(*) as count, COUNT(*) FILTER (WHERE fundingtype IS NULL) as null_count FROM schools WHERE fundingtype IS NOT NULL GROUP BY fundingtype ORDER BY count DESC;
