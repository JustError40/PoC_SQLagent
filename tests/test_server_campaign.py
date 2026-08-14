"""Pure-function tests for the multi-DB server campaign driver."""

from scripts import server_campaign


def _row(run, correct, wrong):
    return {
        "run": run,
        "elapsed_min": 1.0,
        "stages": {},
        "counts": {
            "correct": correct,
            "wrong_answer": wrong,
            "compare_error": 0,
            "clarified": 0,
            "failed_schema": 0,
            "failed_react": 0,
            "failed_llm": 0,
            "failed_other": 0,
        },
        "details": [],
    }


def test_render_db_lists_every_run():
    cfg = {"db_id": "demo", "golden": "evals/demo.golden.jsonl", "run_id": "r1", "database": "demo"}
    md = server_campaign.render_db(cfg, [_row("control", 1, 2), _row("iteration 1", 3, 0)], 3)
    assert "| control | 1 | 2 |" in md
    assert "| iteration 1 | 3 | 0 |" in md


def test_aggregate_reports_baseline_delta():
    results = [{
        "db_id": "demo",
        "run_id": "r1",
        "questions": 3,
        "rows": [_row("control", 1, 2), _row("iteration 5", 3, 0)],
    }]
    md, summary = server_campaign.aggregate(results)
    assert "## demo (3 questions)" in md
    assert "correct 1 → 3 (+2)" in md
    assert summary["dbs"][0]["db_id"] == "demo"
    assert len(summary["dbs"][0]["rows"]) == 2


def test_dotenv_parses_simple_pairs(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("POSTGRES_USER=warehouse\n# comment\nPOSTGRES_PASSWORD='s3cret'\n", encoding="utf-8")
    monkeypatch.setattr(server_campaign, "REPO_ROOT", tmp_path)
    values = server_campaign.dotenv()
    assert values == {"POSTGRES_USER": "warehouse", "POSTGRES_PASSWORD": "s3cret"}
