from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import sql


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DUMP = ROOT / "db_seed" / "demo" / "dvdrental.sql"


def _database_url(url: str, database: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{database}", parts.query, parts.fragment))


def load_dvdrental(dsn: str, dump_path: Path = DEFAULT_DUMP) -> dict[str, object]:
    """Create a separate dvdrental DB and restore the downloaded plain SQL dump."""

    if not dump_path.exists():
        raise FileNotFoundError(dump_path)
    admin_dsn = _database_url(dsn, "postgres")
    target_dsn = _database_url(dsn, "dvdrental")
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = 'dvdrental'").fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier("dvdrental")))

    # The public fixture was produced by a newer pg_dump. PostgreSQL 16 does not
    # know transaction_timeout yet; remove only that session-level directive and
    # preserve the downloaded SQL file byte-for-byte.
    dump = dump_path.read_bytes().replace(b"SET transaction_timeout = 0;\n", b"")
    psql = shutil.which("psql")
    if psql:
        command = [psql, target_dsn, "-v", "ON_ERROR_STOP=1"]
    else:
        command = [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            os.getenv("POSTGRES_USER", "warehouse"),
            "-d",
            "dvdrental",
            "-v",
            "ON_ERROR_STOP=1",
        ]
    completed = subprocess.run(command, input=dump, capture_output=True, check=False)
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).decode(errors="replace")[-4000:]
        raise RuntimeError(f"dvdrental restore failed: {detail}")
    with psycopg.connect(target_dsn) as conn:
        tables = conn.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        ).fetchone()[0]
        rentals = conn.execute("SELECT count(*) FROM public.rental").fetchone()[0]
    return {"database": "dvdrental", "tables": int(tables), "rentals": int(rentals), "dump": str(dump_path)}
