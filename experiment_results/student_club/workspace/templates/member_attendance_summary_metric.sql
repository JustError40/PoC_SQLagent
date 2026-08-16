WITH member_attendance AS (
    SELECT m.member_id, m.first_name, m.last_name, COUNT(a.link_to_event) as events_attended
    FROM member m
    LEFT JOIN attendance a ON a.link_to_member = m.member_id
    GROUP BY m.member_id, m.first_name, m.last_name
)
SELECT first_name, last_name, events_attended
FROM member_attendance
ORDER BY events_attended DESC
LIMIT 10;
