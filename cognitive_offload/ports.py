"""What the app needs from the platform underneath it.

Everywhere else in the core, "where do my files live" was answered by
``Path.home()`` at import time. That answer is correct on a desktop and wrong
on a phone: Android gives an app a private directory and no home folder to put
a dotfile in, and it can move between installs. Asking the platform once, here,
and passing the answer in, is what lets the same storage code run in both
places without an ``if android:`` anywhere.

Nothing in this module imports a UI toolkit, and nothing in it touches disk.
It describes a platform; it does not act on one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Locations:
    """Where this platform keeps the app's files.

    ``home`` is kept alongside the three real paths because it is not storage —
    it is only ever used to shorten a path for display (``~/.cognitive_offload``
    reads better than ``/home/someone/.cognitive_offload``). A platform with no
    meaningful home can pass the data directory and lose nothing but a tilde.
    """

    data_dir: Path
    matrix_dir: Path
    config_file: Path
    home: Path


def desktop_locations(home: Path | str | None = None) -> Locations:
    """The layout this app has always used on Windows, macOS and Linux.

    These values are byte-identical to the module constants they replaced, so
    an existing install finds its own files exactly where it left them. That is
    the whole requirement: a portability change that moved someone's tasks
    would be a data-loss bug wearing an architecture costume.
    """
    root = Path(home).expanduser() if home is not None else Path.home()
    return Locations(
        data_dir=root / ".cognitive_offload",
        matrix_dir=root / "MatrixTasks",
        config_file=root / ".cognitive_offload_config.json",
        home=root,
    )


# Not built yet, and deliberately so — but recorded here because this is the
# module a second front-end reads, and the finding is easy to lose:
#
# app.py hands ``time.monotonic()`` to the focus timer. On Linux — and so on
# Android — CLOCK_MONOTONIC does not advance while the device is suspended,
# while CLOCK_BOOTTIME does (both reachable from the standard library via
# ``time.clock_gettime``). A fifteen-minute block on a phone whose screen
# sleeps would therefore bank fewer minutes than the person actually did,
# which is the exact failure this app spent a release fixing elsewhere: the
# minutes you did are the minutes you keep. A phone host needs to supply
# BOOTTIME. The desktop must keep ``time.monotonic`` — changing it there
# would alter behaviour for no desktop benefit — so this belongs in a Clock
# port, added when there is a seam to plug one into.


def app_private_locations(root: Path | str) -> Locations:
    """Everything under one directory the platform hands you.

    This is the shape Android needs (``Context.getFilesDir()``) and it is also
    what a portable/USB-stick install wants. No dotfiles, nothing written
    outside the directory given, and no assumption that a home folder exists.
    """
    base = Path(root)
    return Locations(
        data_dir=base / "data",
        matrix_dir=base / "MatrixTasks",
        config_file=base / "config.json",
        home=base,
    )
