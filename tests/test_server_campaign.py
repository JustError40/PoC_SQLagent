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
    improvement = summary["dbs"][0]["improvement"]
    assert improvement["baseline_correct"] == 1
    assert improvement["final_correct"] == 3
    assert improvement["delta_correct"] == 2


def test_dotenv_parses_simple_pairs(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("POSTGRES_USER=warehouse\n# comment\nPOSTGRES_PASSWORD='s3cret'\n", encoding="utf-8")
    monkeypatch.setattr(server_campaign, "REPO_ROOT", tmp_path)
    values = server_campaign.dotenv()
    assert values == {"POSTGRES_USER": "warehouse", "POSTGRES_PASSWORD": "s3cret"}


def test_compute_eta_min_uses_mean_duration():
    assert server_campaign.compute_eta_min([10.0, 20.0], 4) == 60.0
    assert server_campaign.compute_eta_min([], 4) is None
    assert server_campaign.compute_eta_min([10.0], 0) is None


def test_render_progress_shows_position_and_counts():
    md = server_campaign.render_progress({
        "campaign_ts": "20260815-000000",
        "branch": "campaign/20260815-000000",
        "updated_at": "2026-08-15T00:00:00+00:00",
        "status": "demo iteration 2 committed",
        "current_db": "demo",
        "db_index": 1,
        "db_total": 3,
        "run_label": "iteration 2",
        "run_index": 3,
        "runs_per_db": 11,
        "last_counts": {"correct": 5},
        "judge_counts": {"incorrect": 1},
        "eta_min": 42.0,
    })
    assert "demo (1/3)" in md
    assert "iteration 2 (3/11)" in md
    assert '"correct": 5' in md
    assert "~42.0 min" in md
