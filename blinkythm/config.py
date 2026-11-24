"""Load and save user settings."""
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
    # prompt conditions
    screen_minutes: float = 20.0      # start checking after this much screen time
    blink_threshold: float = 12.0     # prompt when blinks per minute fall below this
    away_seconds: float = 90.0        # face missing this long counts as away; screen time resets
    snooze_minutes: float = 5.0       # delay after "Later"
    cooldown_minutes: float = 30.0    # no prompts for this long after a game
    # environment
    camera_index: int = 0
    respect_dnd: bool = True          # stay quiet during fullscreen apps and presentations
    monitoring: bool = True
    # game
    latency_offset: float = 0.0       # measured input delay in seconds; positive = input arrives late
    show_guide: bool = True
    volume: float = 0.7
    first_run_done: bool = False
    last_stage: str = ""              # last game played (the home screen suggests the next one)
    records: dict = field(default_factory=dict)   # game -> best accuracy (%)
    stamps: int = 0                   # games finished so far (stamp card)
    daily: dict = field(default_factory=dict)     # {"date", "plays", "rests"} for today

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
