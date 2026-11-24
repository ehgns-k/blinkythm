"""Blinkythm entry point. Run: python main.py  (options: --sim test without a camera, --demo show the prompt quickly, --background start hidden)"""
import argparse
import os
import sys
import traceback

if getattr(sys, "frozen", False) is False:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _fix_std_streams():
        # In a windowed exe there is no console, so stdout/stderr are None and printing would fail
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w"))


def main():
    _fix_std_streams()
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", action="store_true", help="test without a camera; Space acts as a blink")
    ap.add_argument("--demo", action="store_true", help="show the prompt after 12 seconds (settings are not saved)")
    ap.add_argument("--background", action="store_true", help="start with the window hidden")
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
