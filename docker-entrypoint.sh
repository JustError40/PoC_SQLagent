#!/bin/sh
# Build/adapt the skill workspace for the configured DATABASE_URL before serving.
# A fresh container (empty WORKSPACE_PATH volume) surveys and explores its own DB;
# a restarted container with an existing manifest skips straight to the API.
set -e
# The workspace is a bind-mounted git repo owned by the host user; mark it safe
# so in-container git (evolution branches, status) does not fail with
# "detected dubious ownership".
git config --global --add safe.directory "${WORKSPACE_PATH:-/app/skills/warehouse_prod}" 2>/dev/null || true
# Evolution/survey commits into the workspace repo need an identity inside the container.
git config --global user.name "${GIT_AUTHOR_NAME:-sqlagent}" 2>/dev/null || true
git config --global user.email "${GIT_AUTHOR_EMAIL:-sqlagent@localhost}" 2>/dev/null || true
if [ "${BOOTSTRAP_ON_START:-1}" = "1" ]; then
    python -m sqlagent bootstrap
fi
exec "$@"
