SELECT COUNT(*) FROM attendance a
JOIN event e ON a.link_to_event = e.event_id
JOIN member m ON a.link_to_member = m.member_id
JOIN major ma ON m.link_to_major = ma.major_id
WHERE e.event_name = 'Women''s Soccer'
  AND m.t_shirt_size = 'medium'
  AND ma.major_name = 'Student_Club';
