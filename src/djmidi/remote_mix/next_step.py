"""The next step of Mix Together, always in view (golden rule), Qt-free.

The tab holds a lot (connection, tempo, mixer, sound, signals, tracklist). A
DJ should never wonder what to do now: from what is already done, this says
which step comes next, out of four (connect, Link, sound, mix), and which one
action does it.
"""

from __future__ import annotations

from dataclasses import dataclass

HOST, JOIN, LISTEN = "host", "join", "listen"
STEPS = 4

# Step keys (the GUI words them) and the one action each offers, if any.
TYPE_ADDRESS = "type_address"  # join: the host's address is missing
START = "start"  # connect
GIVE_ADDRESS = "give_address"  # host: waiting for the other DJ
WAIT_HOST = "wait_host"  # join: calling the host
LINK = "link"  # connected, but no Link to follow
HEAR = "hear"  # listening clock: send your sound so the app hears your beat
HEARING = "hearing"  # listening clock: sound on, no clear beat yet
SOUND = "sound"  # connected with Link: start the sound
MIXING = "mixing"  # all set

ACTIONS = {
    TYPE_ADDRESS: "focus_address",
    START: "start",
    GIVE_ADDRESS: "copy_address",
    SOUND: "start_sound",
    HEAR: "start_sound",
}


@dataclass(frozen=True)
class State:
    role: str
    running: bool = False
    has_address: bool = False
    connected: bool = False
    link: bool = False
    sound: bool = False
    listening: bool = False  # the beat comes from our listening clock, not Link


@dataclass(frozen=True)
class Step:
    key: str
    number: int  # 1..STEPS

    @property
    def action(self) -> str | None:
        return ACTIONS.get(self.key)


def next_step(state: State) -> Step | None:
    """None for a listener: its own panel says what to do."""
    if state.role == LISTEN:
        return None
    if not state.running:
        if state.role == JOIN and not state.has_address:
            return Step(TYPE_ADDRESS, 1)
        return Step(START, 1)
    if not state.connected:
        return Step(GIVE_ADDRESS if state.role == HOST else WAIT_HOST, 1)
    if not state.link:
        if state.listening:
            return Step(HEARING if state.sound else HEAR, 2)
        return Step(LINK, 2)
    if not state.sound:
        return Step(SOUND, 3)
    return Step(MIXING, 4)
