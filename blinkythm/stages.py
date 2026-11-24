"""미니게임 세 가지의 채보와 설명. 화면 그리기는 game/scenes.py, 판정은 rhythm.py가 맡는다.

세 게임은 입력(눈 깜빡임)은 같고, 박자를 알려 주는 방식이 다르다.
- 등대 신호: 따라 하기. 등대가 한 마디 동안 보낸 신호를 다음 마디에 그대로 돌려준다.
- 올빼미 합창: 이어 가기. 앞의 두 올빼미가 우는 간격만큼 기다렸다가 세 번째로 운다.
- 깜빡 사진관: 일정한 지연. 손님이 종을 치면 언제나 정확히 2박 뒤에 셔터를 누른다.
"""
from dataclasses import dataclass, field
from typing import List

from .rhythm import Cue, Note

COUNT_IN = 4        # 시작 전 4박 세기
TAIL = 2            # 마지막 노트 뒤 여유
PAGE_BEATS = 8      # 가이드 막대 한 쪽의 길이


@dataclass
class Stage:
    key: str
    title: str
    style: str                 # 한 줄 방식 설명(목록에 표시)
    bpm: float
    loop: str                  # 반주 루프 소리 이름
    hit_sound: str             # 잘 맞혔을 때 나는 소리
    howto: List[str]
    sections: List[str]
    cues: List[Cue] = field(default_factory=list)
    notes: List[Note] = field(default_factory=list)
    length: float = 0.0        # 반주가 끝나는 박(노트 마지막 박 이후 첫 마디 경계)

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
        """현재 박에서 다음에 칠 노트의 구간 이름."""
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


# --------------------------------------------------------------------- 등대 신호
# (구간, 4박 안의 박 위치). 한 라운드는 신호 4박 + 응답 4박.
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
        key="lighthouse", title="등대 신호", style="따라 하기", bpm=92, loop="loop_lighthouse",
        hit_sound="ship_bell",
        howto=[
            "밤바다의 등대가 한 마디(4박) 동안 불빛 신호를 보냅니다.",
            "다음 마디에 같은 박자로 눈을 깜빡여 배의 등불로 답하세요.",
            "뱃고동 소리가 신호입니다. 소리와 불빛을 함께 기억하면 쉽습니다.",
        ],
        sections=["정박", "뒷박에서 시작", "엇박"],
    )
    for r, (sec, pat) in enumerate(LIGHTHOUSE_ROUNDS):
        start = COUNT_IN + 8 * r
        for p in pat:
            st.cues.append(Cue(start + p, "horn", "lighthouse"))
            st.notes.append(Note(0, start + 4 + p, sec, reveal=start + p, actor="ship"))
    return st.finish()


# --------------------------------------------------------------------- 올빼미 합창
# (구간, 마디, 마디 안 시작 박, 간격). 첫째가 s, 둘째가 s+d에 울면 플레이어는 s+2d.
OWL_PHRASES = [
    (0, 0, 0, 1), (0, 1, 0, 1), (0, 2, 1, 1), (0, 3, 0, 1),
    (1, 4, 0, 0.5), (1, 4, 2, 0.5), (1, 5, 1, 0.5), (1, 6, 0, 0.5), (1, 6, 2, 0.5), (1, 7, 1, 0.5),
    (2, 8, 0, 1.5), (2, 9, 0, 2), (2, 10, 1, 1), (2, 11, 0, 1.5),
    (3, 12, 0, 1), (3, 12, 2.5, 0.5), (3, 13, 0, 0.5), (3, 13, 1.5, 1),
]


def build_owls():
    st = Stage(
        key="owls", title="올빼미 합창", style="이어 가기", bpm=100, loop="loop_owls",
        hit_sound="hoot_me",
        howto=[
            "나뭇가지의 올빼미 셋이 차례로 눈을 감으며 웁니다. 맨 오른쪽 파란 올빼미가 나입니다.",
            "첫째와 둘째가 운 간격을 그대로 이어서, 같은 간격 뒤에 눈을 깜빡이세요.",
            "간격은 한 박, 반 박, 한 박 반, 두 박으로 바뀝니다.",
        ],
        sections=["한 박 간격", "반 박 간격", "느린 간격", "섞어서"],
    )
    for sec, bar, s, d in OWL_PHRASES:
        b0 = COUNT_IN + bar * 4 + s
        st.cues.append(Cue(b0, "hoot_a", "owl_a"))
        st.cues.append(Cue(b0 + d, "hoot_b", "owl_b"))
        st.notes.append(Note(0, b0 + 2 * d, sec, reveal=b0 + d, actor="owl_me"))
    return st.finish()


# --------------------------------------------------------------------- 깜빡 사진관
PHOTO_DELAY = 2
# (구간, 종이 울리는 박 - COUNT_IN 기준)
PHOTO_BELLS = (
    [(0, b) for b in (0, 4, 8, 12)]
    + [(1, b) for b in (16, 17, 20, 21, 24, 25)]
    + [(2, b) for b in (28, 30.5, 32, 34.5)]
    + [(3, b) for b in (38, 39, 41.5, 43, 44, 46.5, 48, 52, 53)]
)


def build_photo():
    st = Stage(
        key="photo", title="깜빡 사진관", style="2박 뒤에", bpm=112, loop="loop_photo",
        hit_sound="shutter",
        howto=[
            "손님이 책상 위 종을 치면 정확히 2박 뒤에 눈을 깜빡여 셔터를 누르세요.",
            "종이 연달아 울리면 사진도 연달아 찍습니다. 앞 사진을 찍는 동안 다음 종이 울릴 수 있습니다.",
            "종이 박 사이(반 박)에 울려도 셔터는 언제나 2박 뒤입니다.",
        ],
        sections=["한 명씩", "두 명 연달아", "반 박 손님", "섞어서"],
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
    """알림에서 열 때 고를 게임: 지난번 다음 게임을 차례로."""
    if last in ORDER:
        return ORDER[(ORDER.index(last) + 1) % len(ORDER)]
    return ORDER[0]
