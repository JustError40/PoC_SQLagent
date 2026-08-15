SELECT g.country FROM gasstations g JOIN transactions_1k t ON g.gasstationid = t.gasstationid WHERE t.date >= '2013-06-01' AND t.date < '2013-07-01';
