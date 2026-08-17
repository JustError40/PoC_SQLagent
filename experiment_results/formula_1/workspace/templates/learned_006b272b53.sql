SELECT f."School Name", s.street FROM frpm f JOIN schools s ON f.cdscode = s.cdscode WHERE ABS(f."Enrollment (K-12)" - f."Enrollment (Ages 5-17)") > 30 AND s.street IS NOT NULL;
