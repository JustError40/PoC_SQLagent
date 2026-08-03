import pytest

from sqlagent.db import QuerySafetyError, validate_read_only


def test_select_and_cte_are_allowed() -> None:
    assert validate_read_only("SELECT 1;") == "SELECT 1"
    assert validate_read_only("WITH x AS (SELECT 1) SELECT * FROM x")
    assert validate_read_only("-- a grain note\nSELECT 1") == "SELECT 1"


@pytest.mark.parametrize("query", ["UPDATE orders SET status = 'paid'", "DROP TABLE orders", "SELECT 1; SELECT 2"])
def test_writes_and_multiple_statements_are_rejected(query: str) -> None:
    with pytest.raises(QuerySafetyError):
        validate_read_only(query)
