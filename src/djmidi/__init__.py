import sys


def main() -> None:
    # Before the GUI import, so the startup timing log counts import time.
    from djmidi import startup_timing

    startup_timing.begin()
    from djmidi.gui.app import run

    sys.exit(run())
