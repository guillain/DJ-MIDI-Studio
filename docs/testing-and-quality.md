# Testing and Quality

## Table of Contents

- [Quality Goals](#quality-goals)
- [Command Reference](#command-reference)
- [Bash Test Script](#bash-test-script)
- [CI Recommendation](#ci-recommendation)

## Quality Goals

- Keep XML parse/export behavior stable.
- Preserve GUI editing behavior and selection synchronization.
- Prevent regressions in catalog registration and lookup.

## Command Reference

```bash
uv run ruff check src tests
uv run pytest
uv run pytest -q tests/test_parser.py tests/test_exporter.py
```

## Bash Test Script

Use `scripts/test.sh` for common flows:

```bash
bash scripts/test.sh all
bash scripts/test.sh quick
bash scripts/test.sh path tests/test_main_window.py
```

Modes:

- `all`: lint + full tests
- `quick`: lint + fast smoke subset
- `lint`: lint only
- `test`: tests only
- `path <target>`: targeted pytest execution

## CI Recommendation

Run at minimum:

1. `bash scripts/test.sh quick` on each push.
2. `bash scripts/test.sh all` before release tags.

