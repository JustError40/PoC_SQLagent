SELECT COUNT(*) as total_transactions, COUNT(DISTINCT cardid) as unique_cards, COUNT(DISTINCT CASE WHEN cardid IS NOT NULL THEN cardid END) as non_null_cards FROM transactions_1k;
