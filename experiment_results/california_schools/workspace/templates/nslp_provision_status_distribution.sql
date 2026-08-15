SELECT "NSLP Provision Status", COUNT(*) as school_count FROM frpm GROUP BY "NSLP Provision Status" ORDER BY school_count DESC LIMIT 10;
