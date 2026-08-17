SELECT s.cdscode FROM schools s JOIN frpm f ON s.cdscode = f.cdscode GROUP BY s.cdscode HAVING SUM(f."Enrollment (K-12)") > 500;
