from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import sql


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOOLKIT = ROOT / ".cache" / "tpcds-kit"
DEFAULT_DATA = ROOT / ".data" / "tpcds" / "sf10"
DEFAULT_SCALE = 10
TPCDS_TABLES = (
    "call_center", "catalog_page", "catalog_returns", "catalog_sales", "catalog_order",
    "catalog_order_lineitem", "customer", "customer_address", "customer_demographics",
    "date_dim", "dbgen_version", "household_demographics", "income_band", "inventory",
    "item", "promotion", "reason", "ship_mode", "store", "store_returns", "store_sales",
    "time_dim", "warehouse", "web_page", "web_returns", "web_sales", "web_site",
)


def _database_url(url: str, database: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{database}", parts.query, parts.fragment))


def _run(command: list[str], cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def ensure_toolkit(toolkit: Path = DEFAULT_TOOLKIT) -> Path:
    """Download/build only the dsdgen target, tolerating missing yacc for dsqgen."""

    toolkit = toolkit.resolve()
    tools = toolkit / "tools"
    if not tools.exists():
        toolkit.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", "--depth", "1", "https://github.com/gregrahn/tpcds-kit.git", str(toolkit)])
    dsdgen = tools / "dsdgen"
    if not dsdgen.exists():
        _run(
            [
                "make",
                "OS=LINUX",
                "BASE_CFLAGS=-D_FILE_OFFSET_BITS=64 -D_LARGEFILE_SOURCE -DYYDEBUG -fcommon",
                "dsdgen",
            ],
            cwd=tools,
        )
    if not dsdgen.exists():
        raise RuntimeError(f"dsdgen was not built in {tools}")
    return toolkit


def generate_tpcds(
    scale: int = DEFAULT_SCALE,
    data_dir: Path = DEFAULT_DATA,
    toolkit: Path = DEFAULT_TOOLKIT,
    force: bool = False,
) -> dict[str, object]:
    if scale <= 0:
        raise ValueError("TPCDS scale must be positive")
    toolkit = ensure_toolkit(toolkit)
    data_dir = data_dir.resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    existing = list(data_dir.glob("*.dat"))
    if existing and not force:
        return {"status": "already_generated", "scale": scale, "data_dir": str(data_dir), "files": len(existing)}
    if force:
        for path in existing:
            path.unlink()
    command = [
        str(toolkit / "tools" / "dsdgen"),
        "-SCALE", str(scale),
        "-DIR", str(data_dir),
        "-FORCE", "Y",
        "-VERBOSE", "N",
        "-TERMINATE", "N",
    ]
    _run(command, cwd=toolkit / "tools")
    files = sorted(data_dir.glob("*.dat"))
    if not files:
        raise RuntimeError(f"dsdgen generated no .dat files in {data_dir}")
    return {
        "status": "generated",
        "scale": scale,
        "data_dir": str(data_dir),
        "files": len(files),
        "bytes": sum(path.stat().st_size for path in files),
    }


def _psql_command(dsn: str) -> list[str]:
    psql = shutil.which("psql")
    if psql:
        return [psql, dsn, "-v", "ON_ERROR_STOP=1", "-q"]
    container = os.getenv("POSTGRES_CONTAINER", "sqlagent-postgres")
    user = os.getenv("POSTGRES_USER", "warehouse")
    return ["docker", "exec", "-i", container, "psql", "-U", user, "-d", "tpcds", "-v", "ON_ERROR_STOP=1", "-q"]


def _psql_stdin(dsn: str, payload: bytes, extra_args: Iterable[str] = ()) -> None:
    command = _psql_command(dsn)
    if shutil.which("psql"):
        command.extend(extra_args)
    else:
        command.extend(extra_args)
    completed = subprocess.run(command, input=payload, capture_output=True, check=False)
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).decode(errors="replace")[-5000:]
        raise RuntimeError(f"psql failed: {detail}")


def _create_database(dsn: str) -> str:
    admin_dsn = _database_url(dsn, "postgres")
    target_dsn = _database_url(dsn, "tpcds")
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = 'tpcds'").fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier("tpcds")))
    return target_dsn


def load_tpcds(
    dsn: str,
    data_dir: Path = DEFAULT_DATA,
    toolkit: Path = DEFAULT_TOOLKIT,
    replace: bool = False,
) -> dict[str, object]:
    data_dir = data_dir.resolve()
    toolkit = toolkit.resolve()
    schema_path = toolkit / "tools" / "tpcds.sql"
    if not schema_path.exists():
        raise FileNotFoundError(schema_path)
    files = {path.stem: path for path in data_dir.glob("*.dat")}
    missing = [table for table in TPCDS_TABLES if table not in files]
    if missing:
        raise FileNotFoundError(f"missing generated TPC-DS tables: {', '.join(missing[:5])}")
    target_dsn = _create_database(dsn)
    if replace:
        with psycopg.connect(_database_url(dsn, "postgres"), autocommit=True) as conn:
            conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'tpcds' AND pid <> pg_backend_pid()")
            conn.execute("DROP DATABASE IF EXISTS tpcds")
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier("tpcds")))
        target_dsn = _database_url(dsn, "tpcds")
    _psql_stdin(target_dsn, schema_path.read_bytes())
    loaded: dict[str, int] = {}
    for table in TPCDS_TABLES:
        payload = files[table].read_bytes()
        _psql_stdin(target_dsn, payload, ["-c", f"\\copy {table} FROM STDIN WITH (FORMAT csv, DELIMITER '|', NULL '')"])
        loaded[table] = len(payload)
    with psycopg.connect(target_dsn) as conn:
        conn.execute("ANALYZE")
        table_count = conn.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'").fetchone()[0]
    return {"status": "loaded", "database": "tpcds", "tables": int(table_count), "data_dir": str(data_dir), "bytes_by_table": loaded}


def bootstrap_tpcds(
    dsn: str,
    scale: int = DEFAULT_SCALE,
    data_dir: Path = DEFAULT_DATA,
    toolkit: Path = DEFAULT_TOOLKIT,
    force: bool = False,
    replace: bool = False,
) -> dict[str, object]:
    generated = generate_tpcds(scale, data_dir, toolkit, force)
    loaded = load_tpcds(dsn, data_dir, toolkit, replace)
    return {"generated": generated, "loaded": loaded}

