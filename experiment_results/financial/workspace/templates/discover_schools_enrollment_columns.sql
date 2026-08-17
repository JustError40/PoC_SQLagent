SELECT column_name FROM information_schema.columns WHERE table_name = 'schools' AND column_name LIKE '%enroll%' OR column_name LIKE '%count%' OR column_name LIKE '%student%' ORDER BY column_name;
