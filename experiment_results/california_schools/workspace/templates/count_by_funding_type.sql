SELECT fundingtype, COUNT(DISTINCT cdscode) as school_count FROM schools GROUP BY fundingtype ORDER BY school_count DESC;
