#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-all}"

cd "$ROOT_DIR"

run_lint() {
  echo "==> Ruff"
  uv run ruff check src tests
}

run_tests_all() {
  echo "==> Pytest (full suite)"
  uv run pytest
}

run_tests_quick() {
  echo "==> Pytest (quick GUI/core smoke set)"
  uv run pytest -q \
    tests/test_parser.py \
    tests/test_exporter.py \
    tests/test_validator.py \
    tests/test_layout_view.py \
    tests/test_main_window.py
}

run_tests_path() {
  local target="$1"
  echo "==> Pytest (${target})"
  uv run pytest "$target"
}

case "$MODE" in
  all)
    run_lint
    run_tests_all
    ;;
  quick)
    run_lint
    run_tests_quick
    ;;
  lint)
    run_lint
    ;;
  test)
    run_tests_all
    ;;
  path)
    if [[ $# -lt 2 ]]; then
      echo "Usage: $0 path <pytest-target>"
      exit 2
    fi
    run_tests_path "$2"
    ;;
  *)
    cat <<'EOF'
Usage:
  scripts/test.sh all           # lint + full test suite
  scripts/test.sh quick         # lint + fast smoke subset
  scripts/test.sh lint          # lint only
  scripts/test.sh test          # tests only
  scripts/test.sh path <target> # custom pytest target
EOF
    exit 2
    ;;
esac

