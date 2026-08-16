SELECT link_to_member, COUNT(*) as income_count FROM income GROUP BY link_to_member ORDER BY income_count DESC;
