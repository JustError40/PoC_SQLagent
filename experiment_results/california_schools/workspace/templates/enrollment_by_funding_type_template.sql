SELECT schools.fundingtype,
       COUNT(DISTINCT frpm.cdscode) as school_count,
       AVG(frpm."Enrollment (K-12)") as avg_enrollment,
       AVG(frpm."FRPM Count (K-12)") as avg_frpm_count
FROM frpm
JOIN schools ON frpm.cdscode = schools.cdscode
GROUP BY schools.fundingtype;
