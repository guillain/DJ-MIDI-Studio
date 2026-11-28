"""Serato function tags seen in public, Serato-saved MIDI mapping files (issue #194).

Serato publishes no list of its MIDI function tags. These come from other
DJs' mapping XML on GitHub, saved by Serato (``<midi app="...">``) from
version 1.7.8 to 5.0. The maintainer accepted them as real files on
2026-11-28, with the source of each tag kept here. A tag is listed only
when it appears in elements Serato wrote (never in an XML comment) and is
confirmed by a second author's file or by the symbol list extracted from the
Serato binary (rarous/serato-playground ``display/docs/conditionals.csv``,
CC-BY-SA-4.0). Tags seen in a single file only are left out.

Only the tag names are kept (facts), not the files. Generated from the files
by the research of 2026-11-26 (``reports/``); see ``SOURCES``.
"""

from __future__ import annotations

# source key -> (repository, file, Serato version that saved it, licence)
SOURCES: dict[str, tuple[str, str, str, str]] = {
    'spencerthayer:Xml/#01.xml': ('https://github.com/spencerthayer/SeratoDJ-MIDI-Maps', 'Xml/#01.xml', '1.7.8.5433', 'none stated'),
    'rarous:XONEK2 - 4 decks - v4.0.xml': ('https://github.com/rarous/serato-playground', 'XONEK2 - 4 decks - v4.0.xml', '4.0.0.2129', 'CC-BY-SA-4.0'),
    'rarous:XONE K2 - 4 decks (Live FX).xml': ('https://github.com/rarous/serato-playground', 'XONE K2 - 4 decks (Live FX).xml', '2.6.0.1235', 'CC-BY-SA-4.0'),
    'bvandrc:SB3 Custom.xml': ('https://github.com/bvandrc/serato-midi-mapping', 'SB3 Custom.xml', 'Serato DJ Pro 2.3.2.77', 'none stated'),
    'bvandrc:SX2 Custom.xml': ('https://github.com/bvandrc/serato-midi-mapping', 'SX2 Custom.xml', 'Serato DJ Pro 3.2.2.659', 'none stated'),
    'onehundredemoji:serato/launchpad.xml': ('https://github.com/onehundredemoji/midi_maps', 'serato/launchpad.xml', '3.1.1.1260', 'none stated'),
    'retr0nation:retr0 MKII.xml': ('https://github.com/retr0nation/retr0---Novation-launchpad-XML-template', 'retr0 MKII.xml', 'Serato DJ Pro 3.0.12.266', 'none stated'),
    'marscanbueno:marS_PioneerDJMS9v169.xml': ('https://github.com/marscanbueno/serato-dj-pro-midi-maps', 'marS_PioneerDJMS9v169.xml', '2.1.1.25', 'MIT'),
    'davedotdev:serato_lpd8_stems.xml': ('https://github.com/davedotdev/akai_lpd8_serato_stems', 'serato_lpd8_stems.xml', 'Serato DJ Pro 4.0.2.338', 'none stated'),
    'nlpeeee:config/JP-MIDI-MCP-v3.2.xml': ('https://github.com/nlpeeee/JAMJUM-JP-MINI-Serato-stem-control', 'config/JP-MIDI-MCP-v3.2.xml', '5.0.0.950', 'MIT'),
    'djxl:(mapping XML)': ('https://github.com/djxl/Pioneer-DDJ1000SRT-Maps', '(mapping XML)', '2.2.2.03', 'none stated'),
}

# tag -> the source keys of the files it appears in
PUBLIC_TAGS: dict[str, tuple[str, ...]] = {
    'audio_deck_setup_phono': ('marscanbueno:marS_PioneerDJMS9v169.xml',),
    'auto_loop_enable': ('rarous:XONE K2 - 4 decks (Live FX).xml', 'rarous:XONEK2 - 4 decks - v4.0.xml'),
    'auto_loop_length_index': ('rarous:XONEK2 - 4 decks - v4.0.xml',),
    'auto_loop_specific_length': ('bvandrc:SB3 Custom.xml', 'retr0nation:retr0 MKII.xml'),
    'beat_jump': ('bvandrc:SX2 Custom.xml', 'rarous:XONE K2 - 4 decks (Live FX).xml', 'rarous:XONEK2 - 4 decks - v4.0.xml', 'retr0nation:retr0 MKII.xml'),
    'beat_jump_step': ('bvandrc:SB3 Custom.xml', 'bvandrc:SX2 Custom.xml', 'rarous:XONE K2 - 4 decks (Live FX).xml', 'rarous:XONEK2 - 4 decks - v4.0.xml'),
    'censor': ('marscanbueno:marS_PioneerDJMS9v169.xml',),
    'codfather_fx': ('davedotdev:serato_lpd8_stems.xml', 'nlpeeee:config/JP-MIDI-MCP-v3.2.xml', 'retr0nation:retr0 MKII.xml'),
    'codfather_st': ('davedotdev:serato_lpd8_stems.xml', 'nlpeeee:config/JP-MIDI-MCP-v3.2.xml', 'onehundredemoji:serato/launchpad.xml', 'retr0nation:retr0 MKII.xml'),
    'crossfader_curve': ('djxl:(mapping XML)',),
    'cue': ('bvandrc:SB3 Custom.xml', 'rarous:XONE K2 - 4 decks (Live FX).xml'),
    'cue_point': ('onehundredemoji:serato/launchpad.xml', 'spencerthayer:Xml/#01.xml'),
    'cue_point_set': ('onehundredemoji:serato/launchpad.xml', 'spencerthayer:Xml/#01.xml'),
    'dvs_internal_mode': ('spencerthayer:Xml/#01.xml',),
    'dvs_playback_mode_request': ('spencerthayer:Xml/#01.xml',),
    'effect_bank_beats_multiplier': ('bvandrc:SX2 Custom.xml', 'rarous:XONE K2 - 4 decks (Live FX).xml', 'rarous:XONEK2 - 4 decks - v4.0.xml'),
    'effect_bank_channel_assign': ('onehundredemoji:serato/launchpad.xml', 'rarous:XONE K2 - 4 decks (Live FX).xml', 'rarous:XONEK2 - 4 decks - v4.0.xml'),
    'effect_bank_tap_tempo': ('rarous:XONEK2 - 4 decks - v4.0.xml',),
    'effect_level_1_slot_enable': ('rarous:XONEK2 - 4 decks - v4.0.xml',),
    'effect_level_1_slot_parameter_1': ('rarous:XONE K2 - 4 decks (Live FX).xml', 'rarous:XONEK2 - 4 decks - v4.0.xml'),
    'effect_slot_parameter_1': ('rarous:XONE K2 - 4 decks (Live FX).xml',),
    'effect_slot_parameter_2': ('rarous:XONE K2 - 4 decks (Live FX).xml',),
    'effect_slot_parameter_3': ('rarous:XONE K2 - 4 decks (Live FX).xml',),
    'eject': ('bvandrc:SX2 Custom.xml', 'retr0nation:retr0 MKII.xml'),
    'flip_loop_snap': ('onehundredemoji:serato/launchpad.xml',),
    'flip_on_selected': ('onehundredemoji:serato/launchpad.xml',),
    'flip_on_temp': ('onehundredemoji:serato/launchpad.xml',),
    'flip_play_selected': ('onehundredemoji:serato/launchpad.xml',),
    'flip_play_temp': ('onehundredemoji:serato/launchpad.xml',),
    'flip_record': ('onehundredemoji:serato/launchpad.xml',),
    'flip_repeat_selected': ('onehundredemoji:serato/launchpad.xml',),
    'flip_repeat_temp': ('onehundredemoji:serato/launchpad.xml',),
    'flip_save_recording': ('onehundredemoji:serato/launchpad.xml',),
    'flip_slot_iterate': ('onehundredemoji:serato/launchpad.xml',),
    'grid_edit_mode': ('bvandrc:SX2 Custom.xml',),
    'grid_set': ('bvandrc:SB3 Custom.xml', 'bvandrc:SX2 Custom.xml'),
    'instant_double': ('marscanbueno:marS_PioneerDJMS9v169.xml',),
    'key_shift': ('bvandrc:SB3 Custom.xml', 'bvandrc:SX2 Custom.xml', 'onehundredemoji:serato/launchpad.xml'),
    'keylock': ('marscanbueno:marS_PioneerDJMS9v169.xml', 'onehundredemoji:serato/launchpad.xml'),
    'layout_mode': ('rarous:XONEK2 - 4 decks - v4.0.xml',),
    'load_track': ('bvandrc:SB3 Custom.xml', 'rarous:XONE K2 - 4 decks (Live FX).xml', 'rarous:XONEK2 - 4 decks - v4.0.xml', 'spencerthayer:Xml/#01.xml'),
    'load_track_feedback': ('rarous:XONE K2 - 4 decks (Live FX).xml', 'rarous:XONEK2 - 4 decks - v4.0.xml'),
    'loop_length_half_double': ('rarous:XONE K2 - 4 decks (Live FX).xml', 'rarous:XONEK2 - 4 decks - v4.0.xml'),
    'midi_library_scroll': ('rarous:XONE K2 - 4 decks (Live FX).xml', 'rarous:XONEK2 - 4 decks - v4.0.xml', 'spencerthayer:Xml/#01.xml'),
    'modifier_1': ('bvandrc:SB3 Custom.xml',),
    'modifier_3': ('djxl:(mapping XML)',),
    'next_track': ('marscanbueno:marS_PioneerDJMS9v169.xml',),
    'num_decks_displayed': ('bvandrc:SX2 Custom.xml',),
    'pitch_bend_down': ('rarous:XONE K2 - 4 decks (Live FX).xml', 'rarous:XONEK2 - 4 decks - v4.0.xml'),
    'pitch_bend_or_nudge_down': ('rarous:XONE K2 - 4 decks (Live FX).xml', 'rarous:XONEK2 - 4 decks - v4.0.xml'),
    'pitch_bend_or_nudge_up': ('rarous:XONE K2 - 4 decks (Live FX).xml', 'rarous:XONEK2 - 4 decks - v4.0.xml'),
    'pitch_bend_up': ('rarous:XONE K2 - 4 decks (Live FX).xml', 'rarous:XONEK2 - 4 decks - v4.0.xml'),
    'pitch_slider': ('rarous:XONE K2 - 4 decks (Live FX).xml', 'rarous:XONEK2 - 4 decks - v4.0.xml'),
    'play': ('rarous:XONE K2 - 4 decks (Live FX).xml', 'rarous:XONEK2 - 4 decks - v4.0.xml', 'retr0nation:retr0 MKII.xml', 'spencerthayer:Xml/#01.xml'),
    'quantize': ('bvandrc:SB3 Custom.xml', 'nlpeeee:config/JP-MIDI-MCP-v3.2.xml', 'rarous:XONEK2 - 4 decks - v4.0.xml', 'spencerthayer:Xml/#01.xml'),
    'quantize_value_select': ('spencerthayer:Xml/#01.xml',),
    'record_gain': ('bvandrc:SX2 Custom.xml',),
    'sample_player_slot_play': ('retr0nation:retr0 MKII.xml',),
    'sample_player_volume': ('djxl:(mapping XML)',),
    'shift_loop': ('rarous:XONE K2 - 4 decks (Live FX).xml', 'rarous:XONEK2 - 4 decks - v4.0.xml'),
    'slip_mode': ('onehundredemoji:serato/launchpad.xml',),
    'sync': ('rarous:XONE K2 - 4 decks (Live FX).xml', 'rarous:XONEK2 - 4 decks - v4.0.xml', 'retr0nation:retr0 MKII.xml', 'spencerthayer:Xml/#01.xml'),
    'sync_off': ('rarous:XONE K2 - 4 decks (Live FX).xml', 'rarous:XONEK2 - 4 decks - v4.0.xml', 'spencerthayer:Xml/#01.xml'),
    'tab_library': ('spencerthayer:Xml/#01.xml',),
    'toggle_library_mode': ('spencerthayer:Xml/#01.xml',),
    'track_gain': ('bvandrc:SX2 Custom.xml',),
    'widget_cycle': ('spencerthayer:Xml/#01.xml',),
    'widget_mode': ('bvandrc:SB3 Custom.xml', 'bvandrc:SX2 Custom.xml', 'rarous:XONEK2 - 4 decks - v4.0.xml'),
}
