SELECT MAX(b.spent) FROM budget b JOIN event e ON b.link_to_event = e.event_id;
