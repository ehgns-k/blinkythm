"""사용자 설정 저장/불러오기."""
import json
import os
import sys
from dataclasses import dataclass, asdict, field, fields


def config_dir():
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    path = os.path.join(base, "Blinkythm")
    os.makedirs(path, exist_ok=True)
    return path


@dataclass
class Settings:
    # 알림 조건
    screen_minutes: float = 20.0      # 이 시간 이상 화면을 보면 검사 시작
    blink_threshold: float = 12.0     # 분당 깜빡임이 이 값보다 낮으면 알림
    away_seconds: float = 90.0        # 이 시간 이상 얼굴이 안 보이면 자리비움으로 보고 시간 초기화
    snooze_minutes: float = 5.0       # "나중에" 선택 시 재알림 간격
    cooldown_minutes: float = 30.0    # 게임을 한 판 한 뒤 재알림 금지 시간
    # 환경
    camera_index: int = 0
    respect_dnd: bool = True          # 전체 화면/발표 중에는 알리지 않음
    monitoring: bool = True
    # 게임
    latency_offset: float = 0.0       # 보정된 입력 지연(초). 양수 = 입력이 늦게 들어옴
    show_guide: bool = True
    volume: float = 0.7
    first_run_done: bool = False
    last_stage: str = ""              # 마지막으로 한 게임(알림에서 다음 게임을 고를 때 씀)
    records: dict = field(default_factory=dict)   # 게임 -> 최고 정확도(%)
    stamps: int = 0                   # 지금까지 끝낸 판 수(도장판)
    daily: dict = field(default_factory=dict)     # {"date", "plays", "rests"} 오늘 기록

    @classmethod
    def load(cls):
        path = os.path.join(config_dir(), "config.json")
        s = cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            names = {f.name for f in fields(cls)}
            for k, v in data.items():
                if k in names:
                    setattr(s, k, v)
            if not isinstance(s.records, dict):
                s.records = {}
            if not isinstance(s.daily, dict):
                s.daily = {}
        except (OSError, ValueError):
            pass
        return s

    def save(self):
        path = os.path.join(config_dir(), "config.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=2)
        except OSError:
            pass
