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

git pull --ff-only origin main || echo "!! git pull failed; continuing with the local checkout"

PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}" docker compose up -d --build

exec python3 scripts/test_campaign.py
