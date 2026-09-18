# Controller documentation

> 📖 Official references, archived locally so controller documentation remains
> available from the packaged application and without an internet connection.

## Layout

One common directory, one subdirectory per controller, holding everything for
that controller together: its reference artwork and its source PDF(s). The
per-controller image convention is `reference.png` (clean device render,
shown by default) and, where available, `reference-midi.png` (the same view
with the MIDI Message List's callouts printed over it — Controller Images'
"MIDI info" checkbox swaps between them).

```
controllers/
  README.md                 (this file)
  <slug>/
    reference.png
    reference-midi.png      (optional)
    <vendor-doc>.pdf
  custom/                   (Controller Setup exports, see below)
```

`custom/` is reserved for controllers built with the app's **Controller
Setup** tab rather than hand-transcribed from official docs: "Generate
catalog module…" writes `reference_image='custom/<filename>'` into the
generated module, and its completion dialog reminds you to copy the attached
image to `controllers/custom/<filename>` if you want it bundled (respecting
its licence — user-supplied images are your responsibility). Nothing is
copied there automatically.

## MIDI message lists

💡 **Reading the table:** a local copy is the stable in-app reference; the
official link is the provenance source. Product sheets and user guides are
clearly labeled when a MIDI message list was not available. "No profile yet"
means the PDF/artwork is archived here but no `catalog/<slug>.py` module has
been written from it — see `CLAUDE.md` for how to add one from official docs.

| Controller | Local copy | Official source | Status |
| --- | --- | --- | --- |
| DDJ-XP2 | [ddj-xp2/ddj-xp2-midi-message-list-e1.pdf](ddj-xp2/ddj-xp2-midi-message-list-e1.pdf) | [MIDI Message List E1](https://downloads.support.alphatheta.com/software_info/dj-controllers/DDJ-XP2/DDJ-XP2_MIDI_Message_List_E1.pdf) | Archived locally |
| XDJ-XZ | [xdj-xz/xdj-xz-midi-message-list-e3.pdf](xdj-xz/xdj-xz-midi-message-list-e3.pdf) | [MIDI Message List E3](https://downloads.support.alphatheta.com/software_info/all-in-one-dj-systems/XDJ-XZ/XDJ-XZ_MIDI_Message_List_E3.pdf) | Archived locally |
| DDJ-1000 | [ddj-1000/ddj-1000-midi-message-list-e1.pdf](ddj-1000/ddj-1000-midi-message-list-e1.pdf) | [MIDI Message List E1](https://downloads.support.alphatheta.com/software_info/dj-controllers/DDJ-1000/DDJ-1000_MIDI_Message_List_E1.pdf) | Archived locally |
| DDJ-REV1 | [ddj-rev1/ddj-rev1-midi-message-list-e1.pdf](ddj-rev1/ddj-rev1-midi-message-list-e1.pdf) | [MIDI Message List E1](https://downloads.support.alphatheta.com/software_info/dj-controllers/DDJ-REV1/DDJ-REV1_MIDI_Message_List_E1.pdf) | Archived locally |
| DDJ-FLX10 | [ddj-flx10/ddj-flx10-midi-message-list-e1.pdf](ddj-flx10/ddj-flx10-midi-message-list-e1.pdf) | [Pioneer DJ DDJ-FLX10 support](https://www.pioneerdj.com/en/product/controller/ddj-flx10/black/overview/) | Archived locally |
| DDJ-FLX4 | [ddj-flx4/ddj-flx4-midi-message-list-e1.pdf](ddj-flx4/ddj-flx4-midi-message-list-e1.pdf) | Pioneer DJ DDJ-FLX4 MIDI Message List E1 | Archived locally; catalog data not yet cross-checked against it (tracked in issue #11) |
| Numark Mixtrack Pro FX | [numark-mixtrack-pro-fx/numark-mixtrack-pro-fx-user-guide-v1.2.pdf](numark-mixtrack-pro-fx/numark-mixtrack-pro-fx-user-guide-v1.2.pdf) | [MixTrack Pro FX User Guide PDF](https://cdn.inmusicbrands.com/Numark/vAC9uYWEnT/mtprfx/MixTrackProFX-UserGuide-v1.2.pdf) | User guide archived; no MIDI message list located |
| Hercules DJControl Inpulse 500 | [hercules-djcontrol-inpulse-500/hercules-djcontrol-inpulse-500-product-sheet-fr.pdf](hercules-djcontrol-inpulse-500/hercules-djcontrol-inpulse-500-product-sheet-fr.pdf) | [Product Sheet PDF](https://www.hercules.com/wp-content/uploads/2020/06/DJControl_Inpulse_500_Product_Sheet_FR.pdf) | Archived locally; catalog data not yet cross-checked against it (tracked in issue #11) |
| DDJ-REV5 | [ddj-rev5/ddj-rev5-midi-message-list-e1.pdf](ddj-rev5/ddj-rev5-midi-message-list-e1.pdf) | Pioneer DJ DDJ-REV5 MIDI Message List E1 | Archived locally; **no catalog module yet** (issue #12) |
| DDJ-800 | [ddj-800/ddj-800-midi-message-list-e3.pdf](ddj-800/ddj-800-midi-message-list-e3.pdf) | Pioneer DJ DDJ-800 MIDI Message List E3 | Archived locally; **no catalog module yet** (issue #12) |
| Native Instruments Traktor Kontrol S2 MK3 | [traktor-kontrol-s2-mk3/traktor-kontrol-s2-mk3-manual.pdf](traktor-kontrol-s2-mk3/traktor-kontrol-s2-mk3-manual.pdf) | Native Instruments Traktor Kontrol S2 MK3 Manual (English) | Archived locally; **no catalog module yet** (issue #12) |

## How to extend this index

When adding a controller, create `controllers/<slug>/`, drop the archived PDF
and reference artwork in it (record the exact vendor URL when known, and note
whether it is a MIDI message list, a user guide, or only a physical product
reference — a product image must not be described as an annotated MIDI map),
and add a row to the table above. The native application bundles this whole
directory and exposes each available local file through Controller Images >
Open documentation. Until a message list or hardware capture exists, keep the
corresponding profile conservative and mark it as provisional in `TODO.md`.
