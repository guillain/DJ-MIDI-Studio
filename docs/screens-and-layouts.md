# Screens and Layouts

## Table of Contents

- [Application Navigation](#application-navigation)
- [Dashboard](#dashboard)
- [Mapping Views](#mapping-views)
- [Controller Setup](#controller-setup)
- [Controller Images](#controller-images)
- [Live Monitor](#live-monitor)
- [Metronome](#metronome)

## Application Navigation

The application is organized as tabs across the top of the main window:

`Dashboard`, `Controller Setup`, `Controller Images`, `By Channel`, `By Deck`, `By Controller`, `Live Monitor`, and `Metronome`.

The right-hand panel remains available from every tab for the current selection and validation messages. Selecting a mapping or a layout cell keeps the related views synchronized.

![Dashboard and application tab navigation](images/layout/introduction.png)

## Dashboard

The Dashboard shows the loaded Serato file, the registered controllers, catalog statistics, MIDI availability indicators, and shortcuts into the detailed views. A controller card can open its channel tree, controller layout, or reference image. The active controller selector controls those drill-down actions. Availability is detected from the currently listed MIDI input ports; `MIDI: available` means a port name matches the controller catalog, while `MIDI: not detected` means no match was found.

The current catalog contains DDJ-XP2, XDJ-XZ, DDJ-1000, Numark Mixtrack Pro FX, and Hercules DJControl Inpulse 500. Controller Setup definitions applied during the current session also appear here immediately.

## Mapping Views

### By Channel

By Channel is the most granular editing view. It presents the raw MIDI controls grouped by channel and exposes the underlying `Control`, `UserIO`, and mapping hierarchy. Use it when an individual XML mapping must be inspected or edited precisely.

### By Deck

By Deck groups duplicate Serato trigger sets by deck and slot. The upper area contains one tree per deck, while the lower layout area shows the physical controls for the selected controller. The horizontally scrollable controller selector and deck filter allow the physical view to be narrowed to a specific device or deck, even when many controller plugins are installed.

![By Deck mapping view](images/layout/by-deck.png)

### By Controller

By Controller groups catalog entries by physical controller and section, such as `PAD`, `DECK`, or `EFFECT`. The lower schematic maps the selected controller's controls and shows the associated mappings. Its controller selector scrolls horizontally as the dynamic catalog grows. Selecting a physical control highlights the corresponding entries across the mapping views.

![By Controller mapping view](images/layout/by-controller.png)

## Controller Setup

Controller Setup is used to learn MIDI triggers from hardware or import raw triggers from a Serato XML file. The captured table records the section, physical name, MIDI type, channel(s), data value, source, and device.

The same tab provides MIDI output controls for sending a command once, sending a NOTE double-click, replaying selected/all session rows, or generating a catalog module. `Check for conflicts` should be run before applying or exporting a catalog.

![Controller Setup](images/layout/controlleur-etup.png)

## Controller Images

Controller Images displays the official reference diagram for the selected catalog controller. The view supports zooming, panning, and resetting the zoom. The controller selector currently includes DDJ-XP2, XDJ-XZ, and DDJ-1000 when their reference assets are available.

![Controller Images view](images/layout/controlleur-image.png)

## Live Monitor

Live Monitor watches checked MIDI input sources in real time. Use `Refresh ports` to update the list or `Select all sources` to check every currently available input. The monitor can also create a virtual destination for Serato output, provided that destination is added as an additional MIDI output in Serato.

The event table contains the timestamp, direction, source device, MIDI channel and data, followed by the physical control and Serato function resolution. Physical control names are filtered using the source device so that a matching control from another controller is not reported accidentally.

![Live Monitor](images/layout/live-monitor.png)

## Metronome

Metronome replays the current Controller Setup session through a selected MIDI output. It supports one-shot playback of selected or all setup rows, loop playback of selected or all rows, configurable value/velocity, loop frequency, and stopping the loop.

![Metronome](images/layout/metronome.png)
