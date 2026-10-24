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
# A file that gains tr() calls must be added to SOURCES -- so must a Qt-free
# module whose constants are marked with its own QT_TRANSLATE_NOOP (issue #306).
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
  src/djmidi/gui/set_preparation.py
  src/djmidi/gui/audio_preview.py
  src/djmidi/midi_latency.py
  src/djmidi/library/rename.py
  src/djmidi/gui/duplicates_dialog.py
  src/djmidi/gui/health_report_dialog.py
  src/djmidi/controller_sync.py
  src/djmidi/library/set_prep.py
  src/djmidi/library/smart_playlist.py
  src/djmidi/library/health.py
  src/djmidi/gui/help_texts.py
  src/djmidi/gui/help_button.py
  src/djmidi/live_ready.py
  src/djmidi/midi_macros.py
  src/djmidi/library/change_log.py
  src/djmidi/gui/layout_view.py
  src/djmidi/gui/layer_toggles.py
  src/djmidi/gui/live_send.py
  src/djmidi/gui/tree_model.py
  src/djmidi/gui/deck_tree.py
  src/djmidi/gui/controller_tree.py
  src/djmidi/gui/edit_panel.py
  src/djmidi/midi_learn.py
  src/djmidi/gui/function_search_view.py
  src/djmidi/function_search.py
  src/djmidi/gui/controller_image_view.py
  src/djmidi/gui/controller_setup.py
  src/djmidi/gui/controller_submission_dialog.py
  src/djmidi/catalog/codegen.py
  src/djmidi/gui/introduction_view.py
  src/djmidi/gui/live_monitor.py
  src/djmidi/gui/midi_routing_view.py
  src/djmidi/gui/midi_route_transform_dialog.py
  src/djmidi/gui/metronome_view.py
  src/djmidi/gui/controller_emulator.py
  src/djmidi/gui/pad_colour_panel.py
  src/djmidi/validator.py
  src/djmidi/integration_detection.py
  src/djmidi/function_names.py
  src/djmidi/session_player.py
  src/djmidi/gui/macro_editor.py
  src/djmidi/gui/cheat_sheet.py
  src/djmidi/gui/cheat_sheet_dialog.py
  src/djmidi/gui/cheat_sheet_pdf.py
  src/djmidi/mapping_diff.py
  src/djmidi/gui/mapping_diff_dialog.py
  src/djmidi/gui/command_palette.py
  src/djmidi/command_palette.py
  src/djmidi/gui/helpful_notes_dialog.py
  src/djmidi/gui/report_problem_dialog.py
  src/djmidi/gui/safe_update_dialog.py
  src/djmidi/gui/stage_window.py
  src/djmidi/stage.py
  src/djmidi/gui/sync_set_editor.py
  src/djmidi/gui/commands.py
)
LANGUAGES=(fr)

for language in "${LANGUAGES[@]}"; do
  catalogue="src/djmidi/translations/djmidi_${language}.ts"
  uv run pyside6-lupdate -no-obsolete -locations none "${SOURCES[@]}" -ts "$catalogue"
  uv run pyside6-lrelease "$catalogue" -qm "${catalogue%.ts}.qm"
done
