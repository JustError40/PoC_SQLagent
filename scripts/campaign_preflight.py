#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import os
from pathlib import Path

from db_seed.tpcds import DEFAULT_DATA, DEFAULT_SCALE, DEFAULT_TOOLKIT, generate_tpcds


GIB = 1024**3


def available_memory_bytes() -> int:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("cannot determine MemAvailable from /proc/meminfo")


def required_tmpfs_bytes(dataset_bytes: int) -> int:
    # PostgreSQL heap/index/WAL overhead plus explicit operating-system reserve.
    # Measured: SF10 (12 GiB raw .dat) overflowed a 20.75 GiB tmpfs (1.75x)
    # while loading store_sales; 2.6x leaves headroom for WAL and indexes.
    return int(math.ceil((dataset_bytes * 2.6 + GIB) / (256 * 1024**2))) * 256 * 1024**2


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate TPC-DS and size PostgreSQL tmpfs before a campaign")
    parser.add_argument("--scale", type=int, default=int(os.getenv("TPCDS_SCALE", str(DEFAULT_SCALE))))
    parser.add_argument("--data-dir", type=Path, default=Path(os.getenv("TPCDS_DATA_PATH", str(DEFAULT_DATA))))
    parser.add_argument("--toolkit", type=Path, default=Path(os.getenv("TPCDS_TOOLKIT_PATH", str(DEFAULT_TOOLKIT))))
    parser.add_argument("--env-file", type=Path, default=None)
    args = parser.parse_args()
    generate_tpcds(args.scale, args.data_dir, args.toolkit, force=False)
    data_files = list(args.data_dir.glob("*.dat"))
    dataset_bytes = sum(path.stat().st_size for path in data_files)
    if not dataset_bytes:
        raise RuntimeError("TPC-DS generation produced an empty dataset")
    required = required_tmpfs_bytes(dataset_bytes)
    # An explicit POSTGRES_TMPFS_SIZE_BYTES in the environment may raise
    # (never lower) the computed size.
    override = os.getenv("POSTGRES_TMPFS_SIZE_BYTES")
    if override:
        required = max(required, int(override))
    available = available_memory_bytes()
    reserve = max(2 * GIB, int(available * 0.15))
    if required + reserve > available:
        raise SystemExit(
            "insufficient RAM for PostgreSQL tmpfs: "
            f"dataset={dataset_bytes / GIB:.2f} GiB, tmpfs_required={required / GIB:.2f} GiB, "
            f"host_available={available / GIB:.2f} GiB, reserve={reserve / GIB:.2f} GiB; "
            "disk-volume fallback is disabled"
        )
    payload = f"POSTGRES_TMPFS_SIZE_BYTES={required}\nTPCDS_DATASET_BYTES={dataset_bytes}\n"
    if args.env_file is not None:
        args.env_file.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
