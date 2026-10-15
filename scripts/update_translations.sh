#!/usr/bin/env bash
# Refresh the interface translations (issue #263).
#
#   scripts/update_translations.sh
#
# 1. pyside6-lupdate re-reads every source file listed below and adds any new
#    tr() string to src/djmidi/translations/djmidi_<lang>.ts (existing
#    translations are kept; strings no longer in the code are marked obsolete
#    and dropped with -no-obsolete; -locations none keeps line numbers out of
#    the catalogue, so an unrelated edit to a source file never touches it).
# 2. Translate the new <message> entries (Qt Linguist: `uv run pyside6-linguist
#    src/djmidi/translations/djmidi_fr.ts`, or edit the XML by hand).
# 3. Re-run this script: pyside6-lrelease compiles each .ts into the .qm the app
#    loads at launch. Commit both files; tests/test_i18n.py fails when a .qm is
#    older than its .ts or a wrapped string is left untranslated.
#
# A file that gains tr() calls must be added to SOURCES.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SOURCES=(
  src/djmidi/gui/main_window.py
  src/djmidi/gui/preferences_dialog.py
  src/djmidi/gui/first_run_wizard.py
  src/djmidi/gui/live_ready_dialog.py
  src/djmidi/gui/midi_latency_dialog.py
  src/djmidi/gui/layer_map_dialog.py
  src/djmidi/gui/music_library_view.py
  src/djmidi/gui/library_stats_dialog.py
  src/djmidi/gui/rename_files_dialog.py
  src/djmidi/gui/change_history_dialog.py
)
LANGUAGES=(fr)

for language in "${LANGUAGES[@]}"; do
  catalogue="src/djmidi/translations/djmidi_${language}.ts"
  uv run pyside6-lupdate -no-obsolete -locations none "${SOURCES[@]}" -ts "$catalogue"
  uv run pyside6-lrelease "$catalogue" -qm "${catalogue%.ts}.qm"
done
