"""Charts and instructions for the three minigames. Drawing is in game/scenes.py, judging in rhythm.py.

All three use the same input (a blink) but set the beat in different ways.
- Lighthouse: copy. The lighthouse flashes a one-bar signal; answer it in the next bar.
- Owl Choir: continue. Two owls hoot a gap; wait the same gap and hoot third.
- Blink Studio: fixed delay. When a customer rings the bell, take the photo exactly 2 beats later.
"""
from dataclasses import dataclass, field
from typing import List

from .rhythm import Cue, Note


def song_bpm(role, default):
    """Measured tempo of the song for a game (assets/music/music.json), so the chart sits on its beat."""
    from .audio import music_manifest
    return float(music_manifest().get(role, {}).get("bpm", default))

COUNT_IN = 4        # beats counted before the first bar
TAIL = 2            # beats after the last bar
PAGE_BEATS = 8      # beats shown on one page of the guide strip


@dataclass
class Stage:
    key: str
    title: str
    style: str                 # one-word description for the game list
    bpm: float
    song: str                  # music role in assets/music/music.json
    hit_sound: str             # sound for a good hit
    howto: List[str]
    sections: List[str]
    cues: List[Cue] = field(default_factory=list)
    notes: List[Note] = field(default_factory=list)
    length: float = 0.0        # beat where the backing stops (first bar line after the last note)

    @property
    def beat_sec(self):
        return 60.0 / self.bpm

    @property
    def total_beats(self):
        return self.length + TAIL

    @property
    def seconds(self):
        return self.total_beats * self.beat_sec

    def section_at(self, beat):
        """Name of the section of the next note from the given beat."""
        for n in self.notes:
            if n.beat >= beat - 0.5:
                return self.sections[n.section]
        return self.sections[-1]

    def finish(self):
        self.cues.sort(key=lambda c: c.beat)
        self.notes.sort(key=lambda n: n.beat)
        for i, n in enumerate(self.notes):
            n.idx = i
        last = max([n.beat for n in self.notes] + [c.beat for c in self.cues])
        bars = int((last - COUNT_IN) // 4) + 1
        self.length = COUNT_IN + bars * 4
        return self


# --------------------------------------------------------------------- Lighthouse
# (section, beat positions within 4 beats). One round = 4 signal beats + 4 answer beats.
LIGHTHOUSE_ROUNDS = [
    (0, [0, 2]),
    (0, [0, 1, 2]),
    (1, [1, 2, 3]),
    (1, [0.5, 2, 3]),
    (2, [0, 1.5, 3]),
    (2, [0, 1.5, 2.5, 3.5]),
]


def build_lighthouse():
    st = Stage(
        key="lighthouse", title="Lighthouse", style="Copy", bpm=song_bpm("stage_lighthouse", 92), song="stage_lighthouse",
        hit_sound="ship_bell",
        howto=[
            "The lighthouse flashes a signal over one bar (4 beats).",
            "In the next bar, blink the same rhythm to answer with the ship's lamp.",
            "Each flash comes with a foghorn. Remember the sound along with the light.",
        ],
        sections=["On the beat", "Late start", "Off-beat"],
    )
    for r, (sec, pat) in enumerate(LIGHTHOUSE_ROUNDS):
        start = COUNT_IN + 8 * r
        for p in pat:
            st.cues.append(Cue(start + p, "horn", "lighthouse"))
            st.notes.append(Note(0, start + 4 + p, sec, reveal=start + p, actor="ship"))
    return st.finish()


# --------------------------------------------------------------------- Owl Choir
# (section, bar, start beat in bar, gap). First owl at s, second at s+d, the player at s+2d.
OWL_PHRASES = [
    (0, 0, 0, 1), (0, 1, 0, 1), (0, 2, 1, 1), (0, 3, 0, 1),
    (1, 4, 0, 0.5), (1, 4, 2, 0.5), (1, 5, 1, 0.5), (1, 6, 0, 0.5), (1, 6, 2, 0.5), (1, 7, 1, 0.5),
    (2, 8, 0, 1.5), (2, 9, 0, 2), (2, 10, 1, 1), (2, 11, 0, 1.5),
    (3, 12, 0, 1), (3, 12, 2.5, 0.5), (3, 13, 0, 0.5), (3, 13, 1.5, 1),
]


def build_owls():
    st = Stage(
        key="owls", title="Owl Choir", style="Continue", bpm=song_bpm("stage_owls", 87), song="stage_owls",
        hit_sound="hoot_me",
        howto=[
            "Three owls on a branch close their eyes and hoot in turn. You are the blue one on the right.",
            "Keep the gap between the first two hoots and blink after the same gap.",
            "The gap changes between 1, 1/2, 1 1/2 and 2 beats.",
        ],
        sections=["1-beat gap", "Half-beat gap", "Long gap", "Mixed"],
    )
    for sec, bar, s, d in OWL_PHRASES:
        b0 = COUNT_IN + bar * 4 + s
        st.cues.append(Cue(b0, "hoot_a", "owl_a"))
        st.cues.append(Cue(b0 + d, "hoot_b", "owl_b"))
        st.notes.append(Note(0, b0 + 2 * d, sec, reveal=b0 + d, actor="owl_me"))
    return st.finish()


# --------------------------------------------------------------------- Blink Studio
PHOTO_DELAY = 2
# (section, bell beat counted from COUNT_IN)
PHOTO_BELLS = (
    [(0, b) for b in (0, 4, 8, 12)]
    + [(1, b) for b in (16, 17, 20, 21, 24, 25)]
    + [(2, b) for b in (28, 30.5, 32, 34.5)]
    + [(3, b) for b in (38, 39, 41.5, 43, 44, 46.5, 48, 52, 53)]
)


def build_photo():
    st = Stage(
        key="photo", title="Blink Studio", style="2 beats later", bpm=song_bpm("stage_photo", 102), song="stage_photo",
        hit_sound="shutter",
        howto=[
            "When a customer rings the desk bell, blink exactly 2 beats later to take the photo.",
            "Bells can ring back to back, sometimes before the last photo is taken.",
            "Even when a bell rings between beats, the shutter is still 2 beats later.",
        ],
        sections=["One at a time", "Back to back", "Half-beat bells", "Mixed"],
    )
    for k, (sec, b) in enumerate(PHOTO_BELLS):
        at = COUNT_IN + b
        actor = "customer_%d" % (k % 3 + 1)
        st.cues.append(Cue(at, "desk_bell", actor))
        st.notes.append(Note(0, at + PHOTO_DELAY, sec, reveal=at, actor=actor))
    return st.finish()


BUILDERS = {"lighthouse": build_lighthouse, "owls": build_owls, "photo": build_photo}
ORDER = ["lighthouse", "owls", "photo"]
MEDLEY = "medley"


def make_stage(key):
    return BUILDERS[key]()


def next_stage(last):
    """Game the home screen suggests: the one after the last game played."""
    if last in ORDER:
        return ORDER[(ORDER.index(last) + 1) % len(ORDER)]
    return ORDER[0]
