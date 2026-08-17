SELECT s.cdscode, f."High Grade", f."Low Grade" FROM schools s JOIN frpm f ON s.cdscode = f.cdscode ORDER BY s.longitude DESC LIMIT 1;
