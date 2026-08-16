#!/usr/bin/env python3
"""Launcher for the Cognitive Offload desktop app.

The app itself lives in the ``cognitive_offload`` package; this file stays so
``python main.py`` (and run.bat / run.sh) keeps working.
"""

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _fail(message: str) -> "int":
    print(message, file=sys.stderr)
    return 1


def main() -> int:
    if sys.version_info < (3, 9):
        return _fail(f"Python 3.9 or newer is required (running {sys.version.split()[0]}).")
    if importlib.util.find_spec("tkinter") is None:
        return _fail(
            "tkinter is not available for this Python installation.\n"
            "  Debian/Ubuntu: sudo apt install python3-tk\n"
            "  Fedora:        sudo dnf install python3-tkinter\n"
            "  macOS/Windows: reinstall Python from python.org with the Tcl/Tk option."
        )

    import tkinter

    from cognitive_offload.app import main as run_app

    try:
        run_app()
    except tkinter.TclError as exc:
        return _fail(
            f"Could not open a window: {exc}\n"
            "Cognitive Offload needs a graphical desktop session to run."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
