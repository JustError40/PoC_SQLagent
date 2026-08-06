#!/bin/sh
# Build/adapt the skill workspace for the configured DATABASE_URL before serving.
# A fresh container (empty WORKSPACE_PATH volume) surveys and explores its own DB;
# a restarted container with an existing manifest skips straight to the API.
set -e
if [ "${BOOTSTRAP_ON_START:-1}" = "1" ]; then
    python -m sqlagent bootstrap
fi
exec "$@"
