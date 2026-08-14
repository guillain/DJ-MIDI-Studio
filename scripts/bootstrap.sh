#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "==> Bootstrap: SeratoMidiConf"

if ! command -v uv >/dev/null 2>&1; then
  cat <<'EOF'
ERROR: 'uv' is not installed.
Install it first, then re-run this script:
  https://docs.astral.sh/uv/getting-started/installation/
EOF
  exit 2
fi

echo "==> uv version"
uv --version

echo "==> Python version"
uv run python -V

echo "==> Installing dependencies (including dev group)"
uv sync --group dev

echo "==> Ensuring script executability"
chmod +x scripts/test.sh scripts/build.sh scripts/release_artifacts.sh scripts/quality_gate.sh scripts/bootstrap.sh

if [[ -f .git/hooks/pre-commit ]]; then
  echo "==> Existing pre-commit hook found; leaving it untouched"
else
  cat > .git/hooks/pre-commit <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
bash scripts/test.sh quick
HOOK
  chmod +x .git/hooks/pre-commit
  echo "==> Installed .git/hooks/pre-commit (quick lint+tests)"
fi

echo "==> Bootstrap complete"
echo "Next steps:"
echo "  - bash scripts/test.sh quick"
echo "  - uv run seratomidiconf"

