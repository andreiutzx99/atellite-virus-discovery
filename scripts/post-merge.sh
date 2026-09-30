#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

# The base package has no runtime dependencies; install it into Replit's
# project-local Python environment without pulling in optional extras.
python -m pip install \
  --disable-pip-version-check \
  --no-input \
  --no-deps \
  --no-build-isolation \
  --editable .