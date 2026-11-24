"""Shared classic Windows styling. Uses the native theme (vista) and system fonts only."""
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

IS_WIN = sys.platform == "win32"
FONT = "Segoe UI" if IS_WIN else "TkDefaultFont"

# Classic Windows palette. No gradients, shadows or rounded corners.
C_FACE = "#D4D0C8"
C_WHITE = "#FFFFFF"
C_INK = "#000000"
C_GRAY = "#808080"
C_LIGHT = "#F0F0F0"
C_NAVY = "#000080"
C_GREEN = "#008000"
C_OLIVE = "#808000"
C_RED = "#800000"


def setup_style(root):
    style = ttk.Style(root)
    for name in ("vista", "winnative", "clam"):
        if name in style.theme_names():
            style.theme_use(name)
            break
    for fname in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont", "TkFixedFont"):
        try:
            f = tkfont.nametofont(fname)
            if IS_WIN and fname != "TkFixedFont":
                f.configure(family=FONT, size=9)
        except tk.TclError:
            pass
    return style


def bold_font(size=9):
    return (FONT if IS_WIN else "TkDefaultFont", size, "bold")


def plain_font(size=9):
    return (FONT if IS_WIN else "TkDefaultFont", size)


def center_on(win, parent=None, w=None, h=None):
    win.update_idletasks()
    w = w or win.winfo_reqwidth()
    h = h or win.winfo_reqheight()
    if parent is not None and parent.winfo_viewable():
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
    else:
        x = (win.winfo_screenwidth() - w) // 2
        y = (win.winfo_screenheight() - h) // 3
    win.geometry("%dx%d+%d+%d" % (w, h, max(0, x), max(0, y)))


def fmt_hms(sec):
    sec = int(sec)
    return "%02d:%02d:%02d" % (sec // 3600, sec % 3600 // 60, sec % 60)
