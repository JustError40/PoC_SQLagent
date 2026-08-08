#!/bin/sh
# Resume an interrupted TPC-DS test campaign WITHOUT rebuilding or recreating
# the agent containers. Continues from the last completed stage:
#
#   CAMPAIGN_SKIP_STAGES=explore nohup scripts/resume_campaign.sh > campaign.log 2>&1 &
#
# CAMPAIGN_SKIP_STAGES is a comma-separated list of already finished stages
# (survey,explore,optimize,evolve,promote,verify). Question blocks always run.
set -e
cd "$(dirname "$0")/.."

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git pull --ff-only origin main || echo "!! git pull failed; continuing with the local checkout"
fi

exec python3 scripts/test_campaign.py
