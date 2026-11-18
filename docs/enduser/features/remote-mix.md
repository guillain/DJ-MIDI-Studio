# 🌍 Mix together from two places

> Two DJs, two homes, two DJ programs (say Serato on a Mac and Traktor Pro 4
> on Windows), one shared tempo. **Tools → Mix Together…** tests the line
> between you, then keeps your two Ableton Link sessions on one tempo and
> one beat: one DJ leads, the other follows, and you hand the lead over.

📍 [Docs](../../README.md) › [End user](../README.md) › [Features](README.md) › Mix together

## Table of Contents

- [The idea](#the-idea)
- [Phase 0 checklist](#phase-0-checklist)
- [The connection test](#the-connection-test)
- [Reading the lights](#reading-the-lights)
- [One tempo for two homes](#one-tempo-for-two-homes)
- [Hear each other on the grid](#hear-each-other-on-the-grid)
- [What travels](#what-travels)
- [Related](#related)

## The idea

Serato DJ Pro and Traktor Pro both speak **Ableton Link**: same tempo, same
beat. Link is made for one local network, though, and sound over the
internet always arrives late (30 to 120 ms between two cities). The plan:

1. carry Link between the two homes (phase 0 tries a VPN; phase 1, the
   bridge in **Mix Together**, works without one carrying Link);
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

- Both open **Tools → Mix Together…** — see below.
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

**Tools → Mix Together…**, on both computers:

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

## One tempo for two homes

Once the lights answer and Link is on in both DJ programs, a panel appears
under them:

- **Keep our tempos together** (ticked): the DJ who leads sets tempo and
  beat; on the other side the app moves its own Link session onto them, and
  Serato or Traktor follow it like any Link app. The host leads first.
- **Take the lead**: your tempo and beat lead from now on and the other
  side follows — the hand-over of a back-to-back. Change the tempo only on
  the side that leads; the follower's changes are put back.
- **Bar 2 · beat 3 — next phrase in 7**: both windows show the same count
  (phrases of 4 bars of 4 beats), handy to start a track together on the
  first beat of a phrase.

The follower corrects its beat only when it is 3 ms or more off, at most
every two seconds, using the steadiest round trips of the last few seconds,
so a jittery line doesn't make the beat wobble. The **Tempo and phase**
light shows what's left of the gap.

This bridge carries tempo and beat only; the sound comes next.

## Hear each other on the grid

Under the tempo panel, **Hear each other on the grid** sends your master to
the other DJ and plays theirs:

| Setting | What to pick |
|---|---|
| **Send my sound from** | The input that hears your master: a sound-card input fed by your mixer's record or booth output, or a virtual device your DJ software plays into |
| **Play their sound on** | Your speakers or headphones |
| **Program mix to** | Optional: an output for a recorder or a stream (a virtual device such as BlackHole or VB-Cable, read by OBS) |
| **Quality** | **Full, 48 kHz** (about 1.5 Mb/s each way) or **Light, 24 kHz** (about 0.8 Mb/s) for a slow upload |
| **Fine-tune** | Moves their sound a few ms earlier (−) or later (+) if it still sounds off the beat |

Then **Start the sound**, on both sides.

**How it lands on your grid.** Every 5 ms packet carries the sender's Link
beat. The receiver plays it when its own Link beat is one bar further on.
With the two Link sessions on one beat (above), the other DJ is heard exactly
one bar late, whatever the latency of the line, as long as it stays under a
bar (about 1.9 s at 124 BPM). You hear their mix one bar after they play it,
on your grid; they hear yours the same way.

**The mixer.** Volume for you and for them, a level meter each, and a
crossfader. The volume of **Them** sets what you hear; the **Program mix**
is you and them through the crossfader. **Gaps** in the status line count
the sound that didn't arrive in time (played as silence): above a few %,
try **Light** or a cable instead of Wi-Fi.

Not there yet: sound compression (Opus), an EQ and filter per DJ, and
driving the mixer from your controllers.

## What travels

Only this window's own packets, between your two computers: on the port you
chose, clock readings and, with Link, tempo, beat, the number of Link apps
and who leads; once you start the sound, on the next port (47801 by
default), your master as you chose it. Nothing goes anywhere else. No audio, no tracks, no files. Nothing is sent to anyone else.

## Related

- [MIDI routing and clock](midi-routing-and-clock.md)
- [MIDI latency test](midi-latency.md)
- [Live Monitor](live-monitor.md)
