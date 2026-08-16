SELECT major.major_name FROM member m JOIN major ON m.link_to_major = major.major_id WHERE m.first_name = 'Brent' AND m.last_name = 'Thomason';
