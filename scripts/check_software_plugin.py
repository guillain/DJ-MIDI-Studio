"""Check a DJ software plugin against the contract, on real sample files.

    uv run python scripts/check_software_plugin.py PLUGIN_ID SAMPLE [SAMPLE ...]
    uv run python scripts/check_software_plugin.py --import my_plugin PLUGIN_ID samples/*.ext

``--import`` loads an external plugin module first (one not installed in
this environment); built-in plugins are found by their id. Exits 1 when
there is an error, 0 otherwise (warnings and info are printed). See
``docs/developer/design/software-plugins.md``.
"""

from __future__ import annotations

import argparse
import importlib
import sys

from djmidi import software
from djmidi.software import ERROR_SEVERITY, check_software_plugin


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--import", dest="modules", action="append", default=[], help="module that registers it")
    parser.add_argument("plugin_id")
    parser.add_argument("samples", nargs="+")
    args = parser.parse_args(argv)
    software.discover_plugins()
    for module in args.modules:
        importlib.import_module(module)
    try:
        definition = software.get_definition(args.plugin_id)
    except (KeyError, ValueError):
        print(f"No software plugin registered as {args.plugin_id!r}.", file=sys.stderr)
        return 2
    issues = check_software_plugin(definition, args.samples)
    for issue in issues:
        print(issue)
    errors = sum(issue.severity == ERROR_SEVERITY for issue in issues)
    print(f"{definition.name}: {errors} error(s), {len(issues) - errors} other note(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
