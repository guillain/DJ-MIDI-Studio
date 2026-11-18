# 🌍 Mix together from two places

> Two DJs, two homes, two DJ programs (say Serato on a Mac and Traktor Pro 4
> on Windows), one shared tempo. The **Mix Together** tab tests the line
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
   controllers (phase 3), compressed with Opus (phase 4), with an EQ and
   a filter per DJ (phase 5);
3. later: back-to-back signals, a shared tracklist, more than two DJs.

**The plan as a page to share** (in French, with the phase 0 checklist to
tick on both sides, the lights and what's ready):
[Mixer ensemble à 500 km](https://claude.ai/artifact/TbJpiDdRP2T56wZKjzAhSC).
It is private: the maintainer shares it with the other DJ from its Share
menu.

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

- Both open the **Mix Together** tab (also **Tools → Mix Together…**) — see below.
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

In the **Mix Together** tab (also **Tools → Mix Together…**), on both computers:

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
| **Quality** | **Compressed, Opus** (about 0.25 Mb/s each way, the default), **Full, 48 kHz** (about 1.5 Mb/s, uncompressed) or **Light, 24 kHz** (about 0.8 Mb/s) |
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

**Your controller on the mixer.** Press **Learn** next to **Me**, **Them**
or **Crossfader**, then move a fader or knob on your controller: it drives
that mixer control from then on (the button shows it, for example
`ch7 CC 31`). Faders and knobs only (Control Change or pitch bend), never a
pad. **✕** forgets it. The EQ and filter knobs below learn the same way. The assignments are kept in your workspace, and the
mixer only listens: your DJ software still gets every move. Pick a control
your DJ software doesn't use, or one you're happy to move in both places.

**Compression.** **Compressed, Opus** sends your master at 128 kb/s with
5 ms frames: it sounds like the original for a DJ mix and fits almost any
upload. Both of you need this version (v0.48.253 or later): older versions
don't understand the new sound packets. Pick **Full, 48 kHz** for a
local network or a recording where every bit counts.

**EQ and filter.** Under the mixer, each of you has the knobs of a club
mixer channel: **Low**, **Mid** and **High** (full cut to the left, +6 dB to
the right, flat at noon) and a **Filter** (low-pass to the left, high-pass to
the right, off at noon). The other DJ's knobs shape what you hear and the
program mix; yours shape the program mix (your room hears your own mixer as
usual). **Flat** puts a channel back to noon. Every knob has its own
**Learn**, like the faders: your controller's EQ knobs send 64 at their
centre detent, which is noon here too.

**The tab.** Connecting sits on the left (role, addresses, lights, tempo),
**the mixer** at the centre (one channel strip each, crossfader underneath)
and the sound settings on the right once you're connected. On a small
window the three columns stack.

**One mixer for both of you.** Once connected, the mixer is shared: every
move of a volume, an EQ knob, the filter or the crossfader shows up on the
other DJ's screen and in their sound, about as fast as the line (only the
settings travel; each computer already has both sounds). Your own channel
is **Me** on your screen and carries your name on theirs; the crossfader has
each of you on your own left. If you both move the same control, the last
gesture wins, and the line under the mixer says what the other DJ just
moved. A controller assigned with **Learn** waits until you bring it to
where the other DJ left the control before it takes over, so the sound
never jumps.

## What travels

Only this window's own packets, between your two computers: on the port you
chose, clock readings and, with Link, tempo, beat, the number of Link apps
and who leads; once you start the sound, on the next port (47801 by
default), your master as you chose it. No tracks, no files. Nothing is sent to anyone else.

## Related

- [MIDI routing and clock](midi-routing-and-clock.md)
- [MIDI latency test](midi-latency.md)
- [Live Monitor](live-monitor.md)
