from sqlagent.explorer.graph import _extract_corrections
from sqlagent.sqllint import lint_sql, schema_from_tables_yaml


SCHEMA = {
    "store_sales": ["ss_item_sk", "ss_sold_date_sk", "ss_net_profit"],
    "date_dim": ["d_date_sk", "d_date"],
}


def test_valid_join_passes_lint() -> None:
    problems = lint_sql(
        "SELECT d.d_date, sum(ss.ss_net_profit) AS profit FROM store_sales ss "
        "JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk GROUP BY 1",
        SCHEMA,
    )
    assert problems == []


def test_unknown_table_is_caught() -> None:
    problems = lint_sql("SELECT * FROM shipments", SCHEMA)
    assert problems == ["unknown table: shipments"]


def test_unknown_column_is_caught() -> None:
    problems = lint_sql("SELECT ss.ss_ss_sold_date_sk FROM store_sales ss", SCHEMA)
    assert problems
    assert "identifier error" in problems[0]


def test_cte_names_are_not_flagged_as_tables() -> None:
    problems = lint_sql("WITH x AS (SELECT ss_item_sk FROM store_sales) SELECT * FROM x", SCHEMA)
    assert problems == []


def test_system_catalogs_pass_through_to_the_database() -> None:
    assert lint_sql("SELECT table_name FROM information_schema.tables LIMIT 5", SCHEMA) == []
    assert lint_sql("SELECT column_name FROM information_schema.columns WHERE table_name = 'store_sales'", SCHEMA) == []


def test_schema_from_tables_yaml() -> None:
    tables = [{"name": "Orders", "columns": [{"column_name": "id"}, {"column_name": "total"}]}]
    assert schema_from_tables_yaml(tables) == {"orders": ["id", "total"]}


def test_extract_corrections_from_postgres_hint() -> None:
    error = (
        'column "ws_ss_sold_date_sk" does not exist at character 154\n'
        'HINT:  Perhaps you meant to reference the column "ws.ws_sold_date_sk".'
    )
    corrections = _extract_corrections(
        "SELECT * FROM web_sales ws JOIN date_dim d ON ws.ws_ss_sold_date_sk = d.d_date_sk",
        error,
        "SELECT * FROM web_sales ws JOIN date_dim d ON ws.ws_sold_date_sk = d.d_date_sk",
    )
    assert corrections == [{"wrong": "ws_ss_sold_date_sk", "correct": "ws_sold_date_sk", "source": "repair"}]


def test_extract_corrections_ignores_unrelated_errors() -> None:
    assert _extract_corrections("SELECT 1", "syntax error", "SELECT 2") == []
