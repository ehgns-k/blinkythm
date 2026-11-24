"""Windows integration: work area, fullscreen/presentation detection, autostart, DPI. Safe no-ops elsewhere."""
import os
import sys

IS_WIN = sys.platform == "win32"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_NAME = "Blinkythm"


def enable_dpi_awareness():
    if not IS_WIN:
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def work_area(desktop_size):
    """Usable area without the taskbar (left, top, right, bottom). desktop_size is the fallback (w, h)."""
    if IS_WIN:
        import ctypes
        from ctypes import wintypes
        r = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0):
            return r.left, r.top, r.right, r.bottom
    return 0, 0, desktop_size[0], desktop_size[1] - 40


def is_busy():
    """True during fullscreen games or video, presentation mode, or do-not-disturb."""
    if not IS_WIN:
        return False
    import ctypes
    try:
        state = ctypes.c_int(0)
        if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) == 0:
            # 2 busy, 3 D3D fullscreen, 4 presentation mode
            return state.value in (2, 3, 4)
    except Exception:
        pass
    return False


def launch_command():
    if getattr(sys, "frozen", False):
        return '"%s" --background' % sys.executable
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        w = exe[:-10] + "pythonw.exe"
        if os.path.exists(w):
            exe = w
    main = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    return '"%s" "%s" --background' % (exe, main)


def is_autostart():
    if not IS_WIN:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, _RUN_NAME)
            return True
    except OSError:
        return False


def set_autostart(enable):
    if not IS_WIN:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enable:
                winreg.SetValueEx(k, _RUN_NAME, 0, winreg.REG_SZ, launch_command())
            else:
                try:
                    winreg.DeleteValue(k, _RUN_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
