"""Blinkythm - 눈 깜빡임 리듬. 실행: python main.py  (옵션: --sim 카메라 없이 시험, --demo 알림을 빨리 확인, --background 숨김 시작)"""
import argparse
import os
import sys
import traceback

if getattr(sys, "frozen", False) is False:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _fix_std_streams():
    # 콘솔 없는 창 모드(exe)에서는 stdout/stderr가 None이라 출력 시 오류가 난다
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w"))


def main():
    _fix_std_streams()
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", action="store_true", help="카메라 없이 스페이스바로 시험")
    ap.add_argument("--demo", action="store_true", help="12초만 지나도 알림이 뜨도록 조건을 낮춤(설정은 저장되지 않음)")
    ap.add_argument("--background", action="store_true", help="창을 숨기고 시작")
    a = ap.parse_args()
    try:
        from blinkythm.app import App
        App(sim=a.sim, demo=a.demo, background=a.background).run()
    except Exception:
        try:
            from blinkythm.config import config_dir
            with open(os.path.join(config_dir(), "error.log"), "a", encoding="utf-8") as f:
                f.write(traceback.format_exc() + "\n")
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
