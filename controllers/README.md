# Controller documentation

> 📖 Official references, archived locally so controller documentation remains
> available from the packaged application and without an internet connection.

## Layout

One common directory, with real devices grouped by manufacturer under
`hardware/<vendor>/<Model>/`, each holding everything for that controller
together: its reference artwork and its source PDF(s). The vendor folder is
lowercase (`pioneer`, `behringer`, `native-instruments`); the model folder
keeps the name printed on the device (`DDJ-XP2`, `CMD-micro`, `nanoPAD2`). The
per-controller image convention is `reference.png` (clean device render,
shown by default) and, where available, `reference-midi.png` (the same view
with the MIDI Message List's callouts printed over it — the `MIDI` display
layer shows it).

Both are normalized by `scripts/process_controller_images.py`: cropped to the
controller with a 1 % margin and resized to **2000 px wide**. The photo gets
a transparent background (outside the device's outline only, so a line
drawing keeps its white inside); the MIDI picture stays on white, since its
titles and callouts are dark text. Run the script on a new image **before**
measuring its layout: the layout positions are fractions of the processed
image.

```
controllers/
  README.md                 (this file)
  hardware/
    <vendor>/
      <Model>/
        reference.png
        reference-midi.png  (optional)
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
| DDJ-XP2 | [hardware/pioneer/DDJ-XP2/ddj-xp2-midi-message-list-e1.pdf](hardware/pioneer/DDJ-XP2/ddj-xp2-midi-message-list-e1.pdf) | [MIDI Message List E1](https://downloads.support.alphatheta.com/software_info/dj-controllers/DDJ-XP2/DDJ-XP2_MIDI_Message_List_E1.pdf) | Archived locally |
| XDJ-XZ | [hardware/pioneer/XDJ-XZ/xdj-xz-midi-message-list-e3.pdf](hardware/pioneer/XDJ-XZ/xdj-xz-midi-message-list-e3.pdf) | [MIDI Message List E3](https://downloads.support.alphatheta.com/software_info/all-in-one-dj-systems/XDJ-XZ/XDJ-XZ_MIDI_Message_List_E3.pdf) | Archived locally |
| DDJ-1000 | [hardware/pioneer/DDJ-1000/ddj-1000-midi-message-list-e1.pdf](hardware/pioneer/DDJ-1000/ddj-1000-midi-message-list-e1.pdf) | [MIDI Message List E1](https://downloads.support.alphatheta.com/software_info/dj-controllers/DDJ-1000/DDJ-1000_MIDI_Message_List_E1.pdf) | Archived locally |
| DDJ-REV1 | [hardware/pioneer/DDJ-REV1/ddj-rev1-midi-message-list-e1.pdf](hardware/pioneer/DDJ-REV1/ddj-rev1-midi-message-list-e1.pdf) | [MIDI Message List E1](https://downloads.support.alphatheta.com/software_info/dj-controllers/DDJ-REV1/DDJ-REV1_MIDI_Message_List_E1.pdf) | Archived locally |
| DDJ-FLX10 | [hardware/pioneer/DDJ-FLX10/ddj-flx10-midi-message-list-e1.pdf](hardware/pioneer/DDJ-FLX10/ddj-flx10-midi-message-list-e1.pdf) | [Pioneer DJ DDJ-FLX10 support](https://www.pioneerdj.com/en/product/controller/hardware/pioneer/DDJ-FLX10/black/overview/) | Archived locally |
| DDJ-FLX4 | [hardware/pioneer/DDJ-FLX4/ddj-flx4-midi-message-list-e1.pdf](hardware/pioneer/DDJ-FLX4/ddj-flx4-midi-message-list-e1.pdf) | Pioneer DJ DDJ-FLX4 MIDI Message List E1 | Archived locally; catalog data not yet cross-checked against it (tracked in issue #11) |
| Numark Mixtrack Pro FX | [hardware/numark/Mixtrack-Pro-FX/numark-mixtrack-pro-fx-user-guide-v1.2.pdf](hardware/numark/Mixtrack-Pro-FX/numark-mixtrack-pro-fx-user-guide-v1.2.pdf) | [MixTrack Pro FX User Guide PDF](https://cdn.inmusicbrands.com/Numark/vAC9uYWEnT/mtprfx/MixTrackProFX-UserGuide-v1.2.pdf) | User guide archived; no MIDI message list located |
| Numark Mixtrack Pro 3 | [hardware/numark/Mixtrack-Pro-3/reference.png](hardware/numark/Mixtrack-Pro-3/reference.png) | Numbered control diagram (user-guide style), source not recorded | Reference artwork only; **no catalog module** — not to be confused with the Mixtrack Pro FX |
| Hercules DJControl Inpulse 500 | [hardware/hercules/DJControl-Inpulse-500/hercules-djcontrol-inpulse-500-product-sheet-fr.pdf](hardware/hercules/DJControl-Inpulse-500/hercules-djcontrol-inpulse-500-product-sheet-fr.pdf) | [Product Sheet PDF](https://www.hercules.com/wp-content/uploads/2020/06/DJControl_Inpulse_500_Product_Sheet_FR.pdf) | Archived locally; catalog data not yet cross-checked against it (tracked in issue #11) |
| DDJ-REV5 | [hardware/pioneer/DDJ-REV5/ddj-rev5-midi-message-list-e1.pdf](hardware/pioneer/DDJ-REV5/ddj-rev5-midi-message-list-e1.pdf) | Pioneer DJ DDJ-REV5 MIDI Message List E1 | Archived locally; catalog module transcribed from it, not yet verified on hardware (issue #11) |
| DDJ-800 | [hardware/pioneer/DDJ-800/ddj-800-midi-message-list-e3.pdf](hardware/pioneer/DDJ-800/ddj-800-midi-message-list-e3.pdf) | Pioneer DJ DDJ-800 MIDI Message List E3 | Archived locally; catalog module transcribed from it, not yet verified on hardware (issue #11) |
| Behringer CMD LC-1 | [hardware/behringer/CMD-LC-1/reference.png](hardware/behringer/CMD-LC-1/reference.png) (photo + MIDI picture, no document) | No vendor MIDI message list exists | Profile captured from the maintainer's real unit with Controller Setup (all 52 buttons, channel 8) and checked against a real Serato export; real layout measured on its photo |
| Native Instruments Traktor Kontrol S2 MK3 | [hardware/native-instruments/Traktor-Kontrol-S2-MK3/traktor-kontrol-s2-mk3-manual.pdf](hardware/native-instruments/Traktor-Kontrol-S2-MK3/traktor-kontrol-s2-mk3-manual.pdf) | Native Instruments Traktor Kontrol S2 MK3 Manual (English) | Archived locally; **no catalog module yet** (issue #12) |
| Behringer CMD Micro | [hardware/behringer/CMD-micro/cmd-micro-traktor-map.pdf](hardware/behringer/CMD-micro/cmd-micro-traktor-map.pdf) | Behringer CMD Micro Traktor map (control layout only, no MIDI values) | Archived locally; profile captured from the maintainer's unit (20 buttons, channel 1), checked against a real Traktor export |
| Behringer CMD Studio 4a | [hardware/behringer/CMD-studio-4a/cmd-studio-4a-quick-start-guide.pdf](hardware/behringer/CMD-studio-4a/cmd-studio-4a-quick-start-guide.pdf) | Behringer CMD Studio 4a Quick Start Guide (no MIDI table) | Archived locally; profile captured from the maintainer's unit (106 buttons, 4 deck layers), checked against a real Traktor export |
| Korg nanoPAD2 | [hardware/korg/nanoPAD2/nanopad2-midi-implementation.txt](hardware/korg/nanoPAD2/nanopad2-midi-implementation.txt), [chart](hardware/korg/nanoPAD2/nanopad2-midi-implementation-chart.pdf) | Korg nanoPAD2 MIDI Implementation rev. 1.01 + MIDI Implementation Chart (official) | Archived locally; profile captured from the maintainer's unit (all 4 scenes, channel 1) — Korg publishes no note table, pads are user-assignable |

## How to extend this index

When adding a controller, create `controllers/hardware/<vendor>/<Model>/`, drop the archived PDF
and reference artwork in it (record the exact vendor URL when known, and note
whether it is a MIDI message list, a user guide, or only a physical product
reference — a product image must not be described as an annotated MIDI map),
and add a row to the table above. The native application bundles this whole
directory and exposes each available local file through Controller Images >
Open documentation. Until a message list or hardware capture exists, keep the
corresponding profile conservative and mark it as provisional in `TODO.md`.
