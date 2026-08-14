#!/usr/bin/env python3
"""Extract one BIRD mini-dev database from the official PostgreSQL dump.

The dump's naming (quoted mixed-case vs folded lowercase) is inconsistent
across tables, and the shipped PostgreSQL goldens rely on it exactly —
so instead of converting SQLite we cut the chosen db's tables (CREATE TABLE +
COPY data) straight out of MINIDEV_postgresql/BIRD_dev.sql.

Usage: python3 scripts/bird_pg_extract.py --db-id california_schools
Writes .data/bird/<db_id>.pg.sql — load with:
  docker compose -f docker-compose.local.yml exec -T postgres \
    psql -U warehouse -d bird -v ON_ERROR_STOP=1 < .data/bird/<db_id>.pg.sql
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / ".data" / "bird" / "minidev" / "MINIDEV"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-id", required=True)
    parser.add_argument("--data-dir", type=Path, default=DATA)
    args = parser.parse_args()

    tables_json = json.loads((args.data_dir / "dev_tables.json").read_text(encoding="utf-8"))
    entry = next((e for e in tables_json if e["db_id"] == args.db_id), None)
    if entry is None:
        raise SystemExit(f"db_id {args.db_id!r} not found in dev_tables.json")
    wanted = set(entry["table_names_original"])

    dump_path = args.data_dir.parent / "MINIDEV_postgresql" / "BIRD_dev.sql"
    blocks: list[str] = [f"-- BIRD mini-dev / {args.db_id}: extracted from {dump_path.name}\n"]
    found: set[str] = set()
    with dump_path.open(encoding="utf-8") as dump:
        in_block = False
        for line in dump:
            if not in_block:
                for table in wanted:
                    if line.startswith(f"CREATE TABLE public.{table} (") or line.startswith(f"COPY public.{table} "):
                        in_block = True
                        found.add(table)
                        blocks.append(line)
                        break
            else:
                blocks.append(line)
                if line.rstrip("\n") in (");", "\\."):
                    in_block = False

    missing = wanted - found
    if missing:
        raise SystemExit(f"tables not found in dump: {sorted(missing)}")

    drops = "\n".join(f'DROP TABLE IF EXISTS public."{t}" CASCADE;' for t in sorted(wanted))
    out_path = ROOT / ".data" / "bird" / f"{args.db_id}.pg.sql"
    out_path.write_text(drops + "\n\n" + "".join(blocks), encoding="utf-8")
    print(json.dumps({"db_id": args.db_id, "tables": sorted(found), "out": str(out_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
