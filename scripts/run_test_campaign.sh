#!/bin/sh
# Autonomous TPC-DS test campaign runner.
#
# Usage on the server (fully unattended):
#   cd ~/SQLagentPoC
#   nohup scripts/run_test_campaign.sh > campaign.log 2>&1 &
#
# It refreshes the repo, rebuilds and restarts the containers, then runs
# scripts/test_campaign.py, which drives the agent through all learning
# stages and question blocks, writes Results.md and pushes it to GitHub.
set -e
cd "$(dirname "$0")/.."

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git pull --ff-only origin main || echo "!! git pull failed; continuing with the local checkout"
fi

RUN_ID="${RUN_ID:-$(date -u +%Y%m%d-%H%M%S)}"
export RUN_ID
campaign_env_file="$(mktemp)"
trap 'rm -f "$campaign_env_file"' EXIT HUP INT TERM
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}" uv run python scripts/campaign_preflight.py --env-file "$campaign_env_file"
. "$campaign_env_file"
rm -f "$campaign_env_file"
trap - EXIT HUP INT TERM
export POSTGRES_TMPFS_SIZE_BYTES TPCDS_DATASET_BYTES
export TARGET_DB=tpcds

export PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
docker compose build api loader
docker compose up -d postgres
docker compose --profile campaign run --rm loader
docker compose up -d api

exec python3 scripts/test_campaign.py
