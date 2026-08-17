SELECT COUNT(*) FROM frpm WHERE cdscode IS NOT NULL AND 'Enrollment (K-12)' IN (SELECT column_name FROM information_schema.columns WHERE table_name = 'frpm');
