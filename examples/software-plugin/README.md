# Example software plugin

A complete, working DJ MIDI Studio software plugin for a **made-up** format
(`.djmap`, one binding per line). It isn't any real DJ program's format: it
shows, in about 80 lines, everything a plugin for VirtualDJ, Engine DJ or
another program has to do.

- `src/djmidi_example_plugin/__init__.py` — parser, exporter, content
  signature and the `register(...)` call.
- `samples/example.djmap` — a sample file the contract check runs on.
- `pyproject.toml` — the `djmidi.software` entry point that lets DJ MIDI
  Studio find the plugin once installed.

Check it against the contract:

```bash
PYTHONPATH=examples/software-plugin/src uv run python scripts/check_software_plugin.py \
  --import djmidi_example_plugin example.djmap examples/software-plugin/samples/example.djmap
```

The full guide is
[docs/developer/design/software-plugins.md](../../docs/developer/design/software-plugins.md).
