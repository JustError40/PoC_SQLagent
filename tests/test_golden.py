import json

from sqlagent.evaluator import default_corpus_path, generate_golden_cases, rebuild_golden
from sqlagent.workspace import Workspace

TABLES = [
    {
        "name": "orders",
        "columns": [
            {"column_name": "order_id"},
            {"column_name": "customer_id"},
        ],
    },
    {
        "name": "customers",
        "columns": [{"column_name": "customer_id"}],
    },
]

JOINS = [{"left": "orders.customer_id", "right": "customers.customer_id", "verified": True}]


def test_generate_golden_cases_are_deterministic_and_executable_shapes() -> None:
    cases = generate_golden_cases(TABLES, JOINS)
    by_id = {case["id"]: case for case in cases}

    assert by_id["rowcount_orders"]["golden_sql"] == 'SELECT COUNT(*) AS row_count FROM "orders";'
    assert by_id["distinct_orders_order_id"]["golden_sql"] == (
        'SELECT COUNT(DISTINCT "order_id") AS distinct_count FROM "orders";'
    )
    join = by_id["join_orders_customer_id_customers"]
    assert '"orders" JOIN "customers" ON "orders"."customer_id" = "customers"."customer_id"' in join["golden_sql"]
    # same input -> same corpus, no model involved
    assert cases == generate_golden_cases(TABLES, JOINS)


def test_rebuild_golden_writes_corpus_from_workspace_schema(tmp_path) -> None:
    workspace = Workspace(tmp_path / "skill")
    workspace.write_yaml("schema/tables.yaml", {"tables": TABLES})
    workspace.write_yaml("relationships/verified_joins.yaml", {"joins": JOINS})

    report = rebuild_golden(workspace)

    assert report["cases"] == 5
    lines = (workspace.root / "evals" / "golden.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5
    assert all({"id", "question", "golden_sql"} <= set(json.loads(line)) for line in lines)


def test_default_corpus_prefers_workspace_golden(tmp_path) -> None:
    workspace = Workspace(tmp_path / "skill")
    project_root = tmp_path / "project"
    assert default_corpus_path(workspace, project_root) == project_root / "evals" / "regression.jsonl"

    workspace.write_text("evals/golden.jsonl", "{}\n")
    assert default_corpus_path(workspace, project_root) == workspace.root / "evals" / "golden.jsonl"
