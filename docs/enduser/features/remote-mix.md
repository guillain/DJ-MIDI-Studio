# 🌍 Mix together from two places

> Two DJs, two homes, two DJ programs (say Serato on a Mac and Traktor Pro 4
> on Windows), one shared tempo. This page is phase 0: check the line and
> Ableton Link between you with tools that already exist, and measure it
> with the app's connection test, before anything else is built.

📍 [Docs](../../README.md) › [End user](../README.md) › [Features](README.md) › Mix together

## Table of Contents

- [The idea](#the-idea)
- [Phase 0 checklist](#phase-0-checklist)
- [The connection test](#the-connection-test)
- [Reading the lights](#reading-the-lights)
- [What travels](#what-travels)
- [Related](#related)

## The idea

Serato DJ Pro and Traktor Pro both speak **Ableton Link**: same tempo, same
beat. Link is made for one local network, though, and sound over the
internet always arrives late (30 to 120 ms between two cities). The plan:

1. carry Link between the two homes (phase 0 tries a VPN, phase 1 builds a
   bridge into the app);
2. delay the other DJ's sound by exactly one bar minus the line's latency,
   so it lands on your grid (phase 2), with a shared mixer driven from your
   controllers;
3. later: back-to-back signals, a shared tracklist, more than two DJs.

## Phase 0 checklist

Do it together, on the phone, each with a cable (not Wi-Fi) to the box.

**1. One private network for the two of you — ZeroTier**

- Both install ZeroTier One (macOS and Windows).
- One of you creates a network on the ZeroTier website and reads out its
  16-character network ID; the other joins it from the ZeroTier menu.
- The creator authorises both computers on the website. Each now has a
  ZeroTier address (often `10.…` or `172.…`). On Windows, answer **private
  network** if asked.
- ZeroTier carries the multicast Link relies on (Tailscale doesn't), which is
  why it is the one to try.

**2. Link on, both sides**

- **Serato DJ Pro (Mac)**: in **SETUP → DJ Preferences**, turn Sync on
  (Simple or Smart) and **Snap to Beatgrid**, then click **Link** at the top
  left. The deck's SYNC button becomes LINK. On macOS 15 and later, allow
  Serato on the local network (System Settings → Privacy & Security → Local
  Network).
- **Traktor Pro 4 (Windows)**: click **LINK** in the Global Section (shown
  from **Preferences → Global Settings** if it's hidden) and choose
  **BeatSync** in **Preferences → Transport → Sync Mode**. If the downbeat
  lands wrong, map **Reset Downbeat** (Controller Manager → Add In… → Master
  Clock → Ableton Link). Allow Traktor through the Windows firewall on
  private networks.
- Load a track with a beatgrid on each side and change the tempo on one: the
  other should follow. Write down whether it does.

**3. The connection test (this app, both sides)**

- Both open **Tools → Mix Together: Connection Test…** — see below.
- Run it 10 minutes with Link on and a deck playing on each side.

**4. Sound, with an existing tool — SonoBus**

- Both install SonoBus (free, macOS and Windows) and join the same group
  name with a password.
- Its input must hear your master: a sound-card input fed by your mixer's
  record or booth output, or a virtual device (BlackHole on Mac, VB-Cable on
  Windows) chosen as your DJ program's output in its audio settings.
- Play the same kick-only loop on both sides, synced by Link: how far apart
  do the two kicks sound? That gap is what phase 2's one-bar delay will fix.

**Green light for phase 1** when Link follows across, the round trip stays
under 150 ms and the jitter under 20 ms. Send each other the reports either
way: a red result tells what to fix first.

## The connection test

**Tools → Mix Together: Connection Test…**, on both computers:

| Step | Host | The other DJ |
|---|---|---|
| 1 | Tick **I host** | Tick **I join** |
| 2 | Read out one of **Your addresses** (the ZeroTier one) | Type it in **Host's address** |
| 3 | **Start the test** | **Start the test** |

Both sides keep the same **Port** (47800 unless you change it on both). The
first time, Windows and macOS may ask whether DJ MIDI Studio may use the
network: allow it on private networks. Leave **Measure Ableton Link too**
ticked so the test also compares your two Link beats.

**Save the report** writes `remote-mix-test-<date>.md` in your workspace's
`Logs` folder: round trip (min / median / 95 %), jitter, losses, clock
offset spread, both Link tempos, the phase gap between your beats and how it
drifts per minute.

## Reading the lights

- **Network** — round trip and lost packets. Green under 150 ms and 1 %,
  orange under 250 ms and 5 %.
- **Stability** — jitter, how much the round trip moves from one ping to
  the next. Green under 20 ms, orange under 40 ms. This matters most: a steady
  delay can be hidden behind a bar, a moving one can't.
- **Tempo and phase** — with Link on both sides: **green** when both run the
  same tempo with beats less than 5 ms apart (Link reaches across); **red**
  with two different tempos (two separate Link sessions: the VPN doesn't
  carry it, phase 1's bridge will). Grey until Link runs on both sides.

## What travels

Only the test's own small packets, between your two computers, on the port
you chose: clock readings and, with Link, tempo, beat and the number of Link
apps. No audio, no tracks, no files. Nothing is sent to anyone else.

## Related

- [MIDI routing and clock](midi-routing-and-clock.md)
- [MIDI latency test](midi-latency.md)
- [Live Monitor](live-monitor.md)
