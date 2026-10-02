#!/bin/sh
set -eu
TASK_PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
for TASK_SETUP_ARG do
  if [ "$TASK_SETUP_ARG" = '--dry-run' ]; then
    if ! command -v python3 >/dev/null 2>&1; then
      echo 'Preview requires an existing Python 3 interpreter; it will not download one.' >&2
      exit 1
    fi
    exec python3 "$TASK_PROJECT_ROOT/scripts/setup_environment.py" "$@"
  fi
done
if ! command -v uv >/dev/null 2>&1; then
  echo 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/' >&2
  exit 1
fi
exec uv run --no-project --python 3.13 "$TASK_PROJECT_ROOT/scripts/setup_environment.py" "$@"
