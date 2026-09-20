#!/bin/bash
# SessionStart hook for PropertyROI.
# The app itself is standard-library only, so there are no runtime deps to
# install; this prepares the session so tests and the linter run cleanly:
#   - make the package importable from the repo root (PYTHONPATH)
#   - install ruff (the only dev tool) for linting
set -euo pipefail

# Make `import propertyroi` work from anywhere in the session.
echo "export PYTHONPATH=\"${CLAUDE_PROJECT_DIR:-$PWD}:\${PYTHONPATH:-}\"" >> "${CLAUDE_ENV_FILE:-/dev/null}"

# Install the dev linter. Idempotent and quiet; never fail the session if the
# index is briefly unreachable.
python3 -m pip install --quiet --disable-pip-version-check ruff >/dev/null 2>&1 || \
  echo "note: ruff install skipped (offline?); lint may be unavailable this session" >&2

echo "PropertyROI session ready: PYTHONPATH set, ruff available."
