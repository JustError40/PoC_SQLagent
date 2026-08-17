SELECT "School Name", "FRPM Count (K-12)" * 100.0 / "Enrollment (K-12)" AS frpm_participation_rate FROM frpm WHERE "FRPM Count (K-12)" > 0;
