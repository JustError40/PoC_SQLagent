#!/usr/bin/env python3
"""Build a campaign question pack and a golden corpus from BIRD mini-dev dev.json.

Outputs, for a chosen db_id:
- evals/bird_<db_id>.json         — campaign pack (questions only, for test_campaign.py)
- evals/bird_<db_id>.golden.jsonl — reference corpus (id/question/golden_sql) for scoring

Note: golden SQL is the original BIRD SQLite dialect. It must be adapted to
PostgreSQL before it can serve as the scoring reference (separate task).
Only stdlib is used.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-id", required=True)
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".data" / "bird" / "minidev" / "MINIDEV")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "evals")
    parser.add_argument(
        "--exclude-ids",
        type=int,
        nargs="*",
        default=[],
        help="question_id values to drop (e.g. goldens that are invalid in PostgreSQL)",
    )
    args = parser.parse_args()

    # Prefer the PostgreSQL-dialect goldens shipped with mini-dev.
    dev_json = args.data_dir / "mini_dev_postgresql.json"
    if not dev_json.exists():
        dev_json = args.data_dir / "dev.json"
    entries = [
        e
        for e in json.loads(dev_json.read_text(encoding="utf-8"))
        if e.get("db_id") == args.db_id and e.get("question_id") not in args.exclude_ids
    ]
    if not entries:
        raise SystemExit(f"no entries for db_id={args.db_id!r} in {dev_json}")

    questions = []
    for entry in entries:
        text = entry["question"].strip()
        evidence = (entry.get("evidence") or "").strip()
        if evidence:
            text = f"{text}\n(Hint: {evidence})"
        questions.append(text)

    pack = {
        "description": f"BIRD mini-dev: {args.db_id} ({len(questions)} questions)",
        "blocks": [{"name": args.db_id, "title": f"BIRD mini-dev / {args.db_id}", "questions": questions}],
    }
    pack_path = args.out_dir / f"bird_{args.db_id}.json"
    pack_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    dialect = "postgresql" if "postgresql" in dev_json.name else "sqlite"
    golden_path = args.out_dir / f"bird_{args.db_id}.golden.jsonl"
    with golden_path.open("w", encoding="utf-8") as out:
        for entry in entries:
            out.write(json.dumps({
                "id": f"{args.db_id}_{entry['question_id']}",
                "question": entry["question"].strip(),
                "golden_sql": entry["SQL"],
                "dialect": dialect,
            }, ensure_ascii=False) + "\n")

    print(json.dumps({"pack": str(pack_path), "golden": str(golden_path), "questions": len(questions)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
