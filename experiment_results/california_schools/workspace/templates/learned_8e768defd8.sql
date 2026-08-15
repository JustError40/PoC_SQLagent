WITH k8_magnet_schools AS (
    SELECT
        f.cdscode,
        s.city,
        COUNT(DISTINCT f."Educational Option Type") as provision_types
    FROM frpm f
    JOIN schools s ON f.cdscode = s.cdscode
    WHERE s.magnet = 1
      AND f."Low Grade" = 'K'
      AND f."High Grade" = '8'
    GROUP BY f.cdscode, s.city
)
SELECT
    (SELECT COUNT(*) FROM k8_magnet_schools WHERE provision_types > 1) as total_schools_with_multiple_provision_types,
    (SELECT COUNT(DISTINCT city) FROM k8_magnet_schools WHERE provision_types > 1) as number_of_cities,
    city,
    COUNT(*) as school_count
FROM k8_magnet_schools
WHERE provision_types > 1
GROUP BY city;
