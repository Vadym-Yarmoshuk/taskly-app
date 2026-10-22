#!/usr/bin/env bash
# Runs backend or frontend unit tests for the agent.
# Usage: run-tests.sh backend|frontend [test paths relative to the suite dir]
# AGENT_TEST_SANDBOX=docker runs the suite in a container without network
# access or environment variables; otherwise it runs locally without secrets.
set -uo pipefail

suite="${1:-}"
shift || true
root="${AGENT_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
max_lines="${AGENT_TEST_OUTPUT_LINES:-80}"

case "$suite" in
  backend)  test_re='^tests/([A-Za-z0-9_]+/)*test_[A-Za-z0-9_]+\.py$' ;;
  frontend) test_re='^src/([A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.test\.tsx?$' ;;
  *) echo "Usage: run-tests.sh backend|frontend [test paths]" >&2; exit 2 ;;
esac

for path in "$@"; do
  if [[ ! "$path" =~ $test_re ]]; then
    echo "Rejected test path: $path" >&2
    exit 2
  fi
done

if [[ "$suite" == backend ]]; then
  local_cmd=(python -m pytest -q -p no:cacheprovider "$@")
  [[ -x "$root/backend/.venv/bin/python" ]] && local_cmd[0]="$root/backend/.venv/bin/python"
  [[ -x "$root/backend/.venv/Scripts/python.exe" ]] && local_cmd[0]="$root/backend/.venv/Scripts/python.exe"
  sandbox_image="${AGENT_PYTHON_IMAGE:-python:3.13-slim}"
  sandbox_cmd=(.venv/bin/python -m pytest -q -p no:cacheprovider "$@")
else
  local_cmd=(npx --no-install vitest run "$@")
  sandbox_image="${AGENT_NODE_IMAGE:-node:22-slim}"
  sandbox_cmd=(node_modules/.bin/vitest run "$@")
fi

output="$(mktemp)"
trap 'rm -f "$output"' EXIT

if [[ "${AGENT_TEST_SANDBOX:-}" == docker ]]; then
  docker run --rm --network none --user "$(id -u):$(id -g)" \
    -e HOME=/tmp -e CI=true \
    -v "$root:/work" -w "/work/$suite" \
    "$sandbox_image" "${sandbox_cmd[@]}" >"$output" 2>&1
  status=$?
else
  (cd "$root/$suite" && env -u GEMINI_API_KEY -u GOOGLE_API_KEY -u GITHUB_TOKEN -u GH_TOKEN \
    CI=true "${local_cmd[@]}") >"$output" 2>&1
  status=$?
fi

tail -n "$max_lines" "$output"
if [[ $status -eq 0 ]]; then
  echo "RESULT: passed"
else
  echo "RESULT: failed (exit $status)"
fi
exit "$status"
