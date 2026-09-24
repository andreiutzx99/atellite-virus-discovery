#!/bin/sh
# Python executable may be overridden with an absolute path (including spaces).
set -eu
cd -- "$(dirname -- "$0")"
if [ -x .venv/bin/python ]; then
    exec .venv/bin/python -m satellite_discovery.review_ui "$@"
fi
exec "${SATELLITE_PYTHON:-python3}" -m satellite_discovery.review_ui "$@"
