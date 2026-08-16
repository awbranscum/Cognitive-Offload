"""Persistence: config, the main JSON state file and the matrix file store.

No tkinter here either - failures are raised as :class:`StorageError` and the
UI decides how to report them.
"""

from __future__ import annotations

import errno
import json
import os
import re
import shutil
import socket
import tempfile
import time
from pathlib import Path

from .models import MatrixTask, Note, Task, now_stamp
from .ports import Locations, desktop_locations

STATE_VERSION = 2

# The desktop layout, resolved once at import exactly as it always was. Code
# that wants to be told where to write takes a Locations instead; these remain
# so that every existing caller keeps finding the same files.
DEFAULT_LOCATIONS = desktop_locations()
DEFAULT_DB_PATH = DEFAULT_LOCATIONS.data_dir
DEFAULT_MATRIX_PATH = DEFAULT_LOCATIONS.matrix_dir
CONFIG_PATH = DEFAULT_LOCATIONS.config_file

STATE_FILENAME = "data.json"
SESSIONS_FILENAME = "sessions.json"
COMPLETED_LOG_LIMIT = 200

# The bridge out of high-stimulation activity: a few small, concrete steps
# between where you are and the task, so starting is not one big leap.
DEFAULT_WARMUP_STEPS = [
    "Stand up — stretch, water, a lap of the room",
    "Clear the desk and close the tabs that are shouting",
    "Open the file and read one line of it",
]

# key -> (folder name, short label, long label)
CATEGORIES: dict[str, tuple[str, str, str]] = {
    "do_first": ("DoFirst", "Do First", "Do First (Urgent / Important)"),
    "schedule": ("Schedule", "Schedule", "Schedule (Not Urgent / Important)"),
    "delegate": ("Delegate", "Delegate", "Delegate (Urgent / Not Important)"),
    "eliminate": ("Eliminate", "Eliminate", "Eliminate (Not Urgent / Not Important)"),
}
CATEGORY_KEYS = tuple(CATEGORIES)


class StorageError(Exception):
    """Raised when data cannot be read from or written to disk."""


def display_path(path, limit: int = 58, home=None) -> str:
    """Shorten a path for a label: ``~`` for home, an ellipsis for the rest.

    ``home`` defaults to the running user's, which is what every current caller
    wants; a platform whose files live somewhere else passes its own so the
    label still shortens instead of showing an absolute path nobody recognises.
    """
    text = str(path)
    home = str(home if home is not None else Path.home())
    if text.startswith(home):
        text = "~" + text[len(home):]
    if len(text) > limit:
        text = "…" + text[-(limit - 1):]
    return text


def category_label(category: str, long: bool = False) -> str:
    entry = CATEGORIES.get(category)
    if not entry:
        return category.replace("_", " ").title()
    return entry[2] if long else entry[1]


def atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` without risking a truncated file.

    The old code wrote straight into the target, so an error (or a crash)
    mid-write destroyed the previous contents.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # errors="replace": a lone surrogate (astral emoji mangled by some Tk
    # builds, or a \ud83d escape hand-edited into a file) costs one U+FFFD
    # instead of an unsaveable session and a permanently dead autosave.
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", errors="replace",
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp",
        delete=False,
    )
    try:
        with handle as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(handle.name, path)
    except BaseException:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise


def write_json(path: Path, data, indent: int = 2) -> None:
    atomic_write_text(path, json.dumps(data, indent=indent, ensure_ascii=False))


def read_json(path: Path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


class Config:
    """User preferences, stored next to the home directory."""

    def __init__(self, path: Path | None = None, locations: Locations | None = None):
        # A platform describes itself once, here; everything below reads its
        # answer rather than asking the operating system a second time.
        self.locations = locations or DEFAULT_LOCATIONS
        self.path = Path(path) if path is not None else self.locations.config_file
        self.db_path = self.locations.data_dir
        self.matrix_db_path = self.locations.matrix_dir
        self.show_done = True
        self.sort_order = "priority"
        self.autosave = True
        # Short by design: a 15-minute block is small enough to agree to.
        self.focus_minutes = 15
        self.break_minutes = 5
        self.warmup_steps = list(DEFAULT_WARMUP_STEPS)
        self.show_warmup = True
        # Open the always-on-top pop-out automatically when a session starts.
        self.popout_on_start = False
        self.theme = "light"
        self.calm_mode = False

    @property
    def state_file(self) -> Path:
        return self.db_path / STATE_FILENAME

    @property
    def sessions_file(self) -> Path:
        return self.db_path / SESSIONS_FILENAME

    def load(self) -> "Config":
        """Load config, falling back to defaults for anything unusable."""
        try:
            data = read_json(self.path)
        except FileNotFoundError:
            return self
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            # A corrupt config must never stop the app from starting.
            return self
        if not isinstance(data, dict):
            return self
        self.db_path = _path_or(data.get("db_path"), self.locations.data_dir)
        self.matrix_db_path = _path_or(data.get("matrix_db_path"),
                                       self.locations.matrix_dir)
        self.show_done = bool(data.get("show_done", True))
        order = data.get("sort_order")
        from .queries import DEFAULT_SORT, VALID_SORT_KEYS  # here to avoid an import cycle risk

        self.sort_order = order if order in VALID_SORT_KEYS else DEFAULT_SORT
        self.autosave = bool(data.get("autosave", True))
        self.focus_minutes = _int_or(data.get("focus_minutes"), 15, 1, 120)
        self.break_minutes = _int_or(data.get("break_minutes"), 5, 1, 60)
        steps = data.get("warmup_steps")
        if isinstance(steps, list):
            cleaned = [s.strip() for s in steps if isinstance(s, str) and s.strip()]
            self.warmup_steps = cleaned or list(DEFAULT_WARMUP_STEPS)
        self.show_warmup = bool(data.get("show_warmup", True))
        self.popout_on_start = bool(data.get("popout_on_start", False))
        self.theme = "dark" if data.get("theme") == "dark" else "light"
        self.calm_mode = bool(data.get("calm_mode", False))
        return self

    def save(self) -> None:
        try:
            write_json(
                self.path,
                {
                    "db_path": str(self.db_path),
                    "matrix_db_path": str(self.matrix_db_path),
                    "show_done": self.show_done,
                    "sort_order": self.sort_order,
                    "autosave": self.autosave,
                    "focus_minutes": self.focus_minutes,
                    "break_minutes": self.break_minutes,
                    "warmup_steps": list(self.warmup_steps),
                    "show_warmup": self.show_warmup,
                    "popout_on_start": self.popout_on_start,
                    "theme": self.theme,
                    "calm_mode": self.calm_mode,
                },
            )
        except OSError as exc:
            raise StorageError(f"Could not save settings: {exc}") from exc


def _path_or(value, fallback: Path) -> Path:
    if isinstance(value, str) and value.strip():
        return Path(value).expanduser()
    return fallback


def _int_or(value, fallback: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return fallback


try:  # POSIX
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - exercised on Windows
    _fcntl = None
try:  # Windows
    import msvcrt as _msvcrt
except ImportError:  # pragma: no cover - exercised off Windows
    _msvcrt = None

# Errors that mean "somebody else holds this", as opposed to "this filesystem
# does not do locking". Anything else is treated as the latter, because
# refusing to start over an unexpected errno would be the worse failure.
_BUSY_ERRNOS = frozenset({errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK})


def _take_lock(fd: int) -> bool | None:
    """Try to take an exclusive OS lock: True ours, False taken, None can't.

    ``flock`` is deliberate. POSIX record locks (``fcntl.lockf``) are owned by
    the *process*, so a second lock inside one process succeeds and the guard
    quietly stops guarding — including in this app's own tests. ``flock`` is
    owned by the open file, which is the behaviour wanted here.
    """
    if _fcntl is not None:
        try:
            _fcntl.flock(fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
            return True
        except OSError as exc:
            return False if exc.errno in _BUSY_ERRNOS else None
    if _msvcrt is not None:  # pragma: no cover - Windows only
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            _msvcrt.locking(fd, _msvcrt.LK_NBLCK, 1)
            return True
        except OSError as exc:
            return False if exc.errno in _BUSY_ERRNOS else None
    return None  # pragma: no cover - neither module exists


class InstanceLock:
    """Guards a session folder against a second running copy.

    Two instances autosaving the same ``data.json`` is last-writer-wins data
    loss: every change made in one is silently erased by the other within 30
    seconds. The lock is advisory — a ``.lock`` file with pid/host/started
    inside — and staleness is deliberately the *user's* call: probing pid
    liveness portably is a trap (``os.kill(pid, 0)`` terminates the target
    process on Windows).
    """

    def __init__(self, folder: Path):
        self.path = Path(folder) / ".lock"
        self.owned = False
        # Set when a refusal could not be explained: this filesystem does not
        # do locking, or the file would not open. The caller needs to know the
        # difference, because "a copy is running" and "we cannot tell whether
        # a copy is running" deserve different things said to the person.
        self.uncertain = False
        # Held open for as long as this copy runs: the operating system lock
        # lives on the open file, not on the file's existence, so letting the
        # handle close would hand the lock straight back.
        self._fd: int | None = None

    def _stamp(self) -> dict:
        return {
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "started": now_stamp(),
        }

    def _write_stamp(self, fd: int) -> None:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            os.truncate(fd, 0)
            os.write(fd, json.dumps(self._stamp()).encode("utf-8"))
        except OSError:
            pass

    def acquire(self) -> bool:
        """Take the lock. False only when another copy is genuinely running.

        A lock file left behind by a crash used to be indistinguishable from a
        copy that is running right now, so the next launch opened with a
        question — at exactly the moment the app promises to take a thought
        off your hands. Worse, it was a question nobody can answer: you cannot
        know whether the process that wrote a pid two days ago is alive.

        So the file's existence no longer decides anything. Ownership is an
        operating-system lock held on the open handle, which the kernel drops
        when the holding process dies, however it dies. A running second copy
        is still refused; a crashed one leaves nothing to ask about.
        """
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        except FileExistsError:
            return self._claim_existing()
        except OSError:
            # An unwritable folder will fail loudly at the first save; a
            # second refusal here would just be in the way.
            return True
        # Nobody had the file at all. Take the OS lock if this platform offers
        # one, but do not refuse to start if it does not.
        _take_lock(fd)
        self._fd = fd
        self._write_stamp(fd)
        self.owned = True
        return True

    def _claim_existing(self) -> bool:
        """The file is already there. Is anyone actually behind it?"""
        try:
            fd = os.open(self.path, os.O_RDWR)
        except OSError:
            self.uncertain = True  # cannot even look; say so rather than guess
            return False
        held = _take_lock(fd)
        if held is not True:
            # False means a live copy is holding the lock right now, which we
            # can state as fact. None means this filesystem does not do
            # locking — network and synced folders often do not — and then a
            # leftover file from a crash is still a real possibility. Both
            # refuse; only one of them is certain.
            self.uncertain = held is None
            os.close(fd)
            return False
        # The lock was free, so whoever wrote this file is gone. Claiming it
        # silently is the whole point: there is no question worth asking.
        self._fd = fd
        self._write_stamp(fd)
        self.owned = True
        return True

    def takeover(self) -> None:
        """The user says the other copy is gone: claim the lock anyway.

        Only reachable now when the OS lock could not answer the question —
        a genuinely running copy, or a filesystem that cannot lock. The
        override stays because the second case is real.
        """
        try:
            self.path.write_text(json.dumps(self._stamp()), encoding="utf-8")
        except OSError:
            pass
        self.owned = True

    def holder(self) -> str:
        """Human-readable description of whoever seems to hold the lock."""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return "details unreadable"
        started = data.get("started") or "unknown time"
        host = data.get("host") or ""
        return f"started {started}" + (f" on {host}" if host else "")

    def release(self) -> None:
        """Remove the lock file — only if this instance owns it."""
        if not self.owned:
            return
        try:
            self.path.unlink()
        except OSError:
            pass
        self._close()
        self.owned = False

    def _close(self) -> None:
        """Drop the handle, and with it the OS lock."""
        if self._fd is None:
            return
        try:
            os.close(self._fd)
        except OSError:
            pass
        self._fd = None


class NotASessionError(StorageError):
    """The file is readable, it just isn't ours. Never quarantine these:
    renaming a file that belongs to something else is worse than refusing it."""


class NewerSessionError(NotASessionError):
    """Saved by a newer version of the app. Loading it would silently drop
    whatever the newer format added — and the next autosave would make the
    amputation permanent. Refusing is the only honest answer."""


class StateStore:
    """Reads/writes the tasks + scratchpad document."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._backed_up = False
        self._suspect = False

    def set_path(self, path: Path) -> None:
        self.path = Path(path)
        self._backed_up = False
        self._suspect = False


    @property
    def backup_path(self) -> Path:
        return self.path.with_suffix(self.path.suffix + ".bak")

    def load(self) -> dict:
        """Return ``{"tasks": [...], "scratchpad": str, "timer_minutes": int}``."""
        try:
            data = read_json(self.path)
        except FileNotFoundError:
            return {"tasks": [], "scratchpad": "", "timer_minutes": 15, "completed_log": []}
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            # An unreadable file must never reach _backup(): copying it over
            # the .bak would destroy the last good copy at the exact moment
            # it is needed.
            self._suspect = True
            raise StorageError(f"Could not read {self.path}: {exc}") from exc
        if not isinstance(data, dict):
            raise NotASessionError(f"{self.path} does not contain a saved session")
        if "tasks" not in data and "notes" not in data and "scratchpad" not in data:
            # Valid JSON, but nothing this app wrote. Loading it as an empty
            # session and then autosaving over the file is how data vanishes.
            raise NotASessionError(
                f"{self.path} is JSON, but not a Cognitive Offload session "
                f"(no tasks, notes or scratchpad in it)"
            )
        version = data.get("version")
        if isinstance(version, int) and version > STATE_VERSION:
            raise NewerSessionError(
                f"{self.path} was saved by a newer version of Cognitive "
                f"Offload (format {version}; this one reads up to "
                f"{STATE_VERSION}). Open it with the newer version instead — "
                f"loading it here would drop whatever the newer format added."
            )
        self._suspect = False
        return self.deserialize(data)

    def quarantine(self) -> Path | None:
        """Move an unreadable session file aside instead of leaving it where
        the next save would fight it. Returns the new path, or None if the
        move failed (the file then stays put and stays protected)."""
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = self.path.with_name(f"{self.path.name}.corrupt-{stamp}")
        counter = 0
        while target.exists():
            counter += 1
            target = self.path.with_name(f"{self.path.name}.corrupt-{stamp}-{counter}")
        try:
            self.path.rename(target)
        except OSError:
            return None
        self._suspect = False  # nothing suspect left at self.path
        return target

    def restore_backup(self) -> bool:
        """Copy the .bak back over the session file. True on success."""
        try:
            shutil.copy2(self.backup_path, self.path)
        except OSError:
            return False
        self._suspect = False
        return True

    def preserve_backup(self) -> None:
        """Keep the current .bak for the rest of this run.

        After starting fresh from a quarantined file, the once-per-run backup
        would otherwise copy the brand-new (empty) session over the last good
        .bak on the second save.
        """
        self._backed_up = True

    @staticmethod
    def deserialize(data: dict) -> dict:
        tasks: list[Task] = []
        dropped = 0
        for record in data.get("tasks") or []:
            try:
                task = Task.from_dict(record)
            except (ValueError, TypeError):
                # Counted, not silent: the caller decides whether losing
                # these on the next save needs the user's consent.
                dropped += 1
                continue
            if task.text:
                tasks.append(task)

        scratchpad = data.get("scratchpad")
        if not isinstance(scratchpad, str):
            # Pre-2.0 files kept a list of timestamped notes instead.
            notes = [Note.from_dict(n) for n in data.get("notes") or [] if isinstance(n, dict)]
            scratchpad = "\n".join(n.render() for n in notes)

        finished = []
        for record in data.get("completed_log") or []:
            if isinstance(record, dict) and isinstance(record.get("text"), str):
                finished.append({
                    "text": record["text"],
                    "completed_at": record.get("completed_at") or "",
                })

        return {
            "tasks": tasks,
            "scratchpad": scratchpad,
            # Short by default: 15 minutes is the length you can agree to.
            "timer_minutes": _int_or(data.get("timer_minutes"), 15, 1, 240),
            "completed_log": finished[-COMPLETED_LOG_LIMIT:],
            "dropped": dropped,
        }

    @staticmethod
    def serialize(tasks: list[Task], scratchpad: str, timer_minutes: int,
                  completed_log: list | None = None) -> dict:
        return {
            "version": STATE_VERSION,
            "tasks": [t.to_dict() for t in tasks],
            "scratchpad": scratchpad,
            "timer_minutes": int(timer_minutes),
            # What was finished and then cleared away. Kept so "N done today"
            # survives a tidy-up; capped because it is a footnote, not a store.
            "completed_log": list(completed_log or [])[-COMPLETED_LOG_LIMIT:],
            "saved_at": now_stamp(),
        }

    def save(self, tasks: list[Task], scratchpad: str, timer_minutes: int,
             completed_log: list | None = None) -> None:
        payload = self.serialize(tasks, scratchpad, timer_minutes, completed_log)
        try:
            self._backup()
            write_json(self.path, payload)
        except (OSError, ValueError, TypeError) as exc:
            # ValueError/TypeError: a serialization failure must surface as
            # the same dialog-and-quit path as a disk error, not escape and
            # leave the window unclosable with autosave silently dead.
            raise StorageError(f"Could not save to {self.path}: {exc}") from exc

    def _backup(self) -> None:
        """Keep the session as it was when the app started, as ``.bak``.

        Autosave fires every 30 seconds, so a backup that is refreshed on
        every write is gone long before anyone notices they need it. Writing
        it once per run means the fallback is the state you last opened.
        """
        if self._backed_up or self._suspect or not self.path.exists():
            return
        try:
            shutil.copy2(self.path, self.path.with_suffix(self.path.suffix + ".bak"))
            self._backed_up = True
        except OSError:
            pass  # A missing backup should never block the real save.


_SLUG_RE = re.compile(r"[^A-Za-z0-9._ -]+")


def slugify(name: str, fallback: str = "task") -> str:
    """Filesystem-safe stem for a task title."""
    cleaned = _SLUG_RE.sub("", name).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return (cleaned[:60].strip() or fallback)


class MatrixStore:
    """One folder per quadrant, one ``.task`` JSON file per task.

    Files are named ``<slug>-<id>.task`` so two tasks may share a title and a
    rename never has to move data (the id in the name keeps it unique).
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    def set_root(self, root: Path) -> None:
        self.root = Path(root)

    def ensure(self) -> None:
        try:
            for key in CATEGORY_KEYS:
                self.path_for(key).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError(f"Could not create matrix folders in {self.root}: {exc}") from exc

    def path_for(self, category: str) -> Path:
        if category not in CATEGORIES:
            raise KeyError(f"unknown quadrant: {category}")
        return self.root / CATEGORIES[category][0]

    def list(self, category: str) -> list[MatrixTask]:
        folder = self.path_for(category)
        if not folder.is_dir():
            return []
        tasks: list[MatrixTask] = []
        for path in sorted(folder.glob("*.task")):
            task = self._read(path, category)
            if task is not None:
                tasks.append(task)
        tasks.sort(key=lambda t: (t.created_at, t.title.casefold()))
        return tasks

    def _read(self, path: Path, category: str) -> MatrixTask | None:
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            task = MatrixTask.from_dict(data, category)
        else:
            # Legacy plain-text file: the filename was the title.
            task = MatrixTask(title=path.stem, content=raw, category=category)
        if not task.title:
            task.title = path.stem
        task.category = category
        task.path = path
        return task

    def _new_path(self, category: str, task: MatrixTask) -> Path:
        if not self.root.exists():
            # Recreating the tree under a vanished root (unmounted drive,
            # moved folder) forks the data: new files land in a fresh empty
            # tree while the real one sits somewhere else.
            raise StorageError(
                f"The matrix folder is missing: {self.root} (moved or unmounted?)"
            )
        folder = self.path_for(category)
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{slugify(task.title)}-{task.id[:8]}.task"

    def create(self, category: str, title: str, content: str = "") -> MatrixTask:
        task = MatrixTask(title=title.strip(), content=content, category=category)
        task.path = self._new_path(category, task)
        self._write(task)
        return task

    def update(self, task: MatrixTask, title: str, content: str) -> MatrixTask:
        title = title.strip()
        renamed = title != task.title
        previous = (task.title, task.content, task.updated_at, task.path)
        task.title = title
        task.content = content
        task.updated_at = now_stamp()
        old_path = Path(task.path) if task.path else None
        if renamed or old_path is None:
            task.path = self._new_path(task.category, task)
        self._write(task)
        if renamed and old_path is not None and old_path != Path(task.path):
            try:
                self._unlink(old_path)
            except StorageError:
                # Same guarantee move() gives: never leave the task as two
                # files. Take back the copy and restore the old identity.
                self._unlink_quietly(Path(task.path))
                task.title, task.content, task.updated_at, task.path = previous
                raise
        return task

    def set_scheduled(self, task: MatrixTask, when: str) -> MatrixTask:
        """Book (or clear, with ``""``) the time this task will happen."""
        task.scheduled_for = when or ""
        task.updated_at = now_stamp()
        if task.path is None:
            task.path = self._new_path(task.category, task)
        self._write(task)
        return task

    def move(self, task: MatrixTask, category: str) -> MatrixTask:
        if category == task.category:
            return task
        old_path = Path(task.path) if task.path else None
        previous_category = task.category
        task.category = category
        task.updated_at = now_stamp()
        task.path = self._new_path(category, task)
        self._write(task)
        if old_path is not None:
            try:
                self._unlink(old_path)
            except StorageError:
                # Roll the copy back rather than leave the task in two
                # quadrants, where the next refresh shows it twice.
                self._unlink_quietly(Path(task.path))
                task.category = previous_category
                task.path = old_path
                raise
        return task

    @staticmethod
    def _unlink_quietly(path: Path) -> None:
        try:
            path.unlink()
        except OSError:
            pass

    def delete(self, task: MatrixTask) -> None:
        if task.path:
            self._unlink(Path(task.path))

    def add_from_task(self, category: str, task: Task) -> MatrixTask:
        """Move a main-list task into a quadrant without dropping any fields."""
        created = MatrixTask(
            title=task.text, content=task.description, category=category,
            first_step=task.first_step, kind=task.kind,
            scheduled_for=task.scheduled_for, tags=list(task.tags),
            priority=task.priority, pinned=task.pinned,
            estimate_minutes=task.estimate_minutes,
        )
        created.path = self._new_path(category, created)
        self._write(created)
        return created

    def restore(self, task: MatrixTask) -> MatrixTask:
        """Write a task back after it was moved out — the undo half of delete."""
        if task.path is None:
            task.path = self._new_path(task.category, task)
        self._write(task)
        return task

    def _write(self, task: MatrixTask) -> None:
        try:
            write_json(Path(task.path), task.to_dict())
        except OSError as exc:
            raise StorageError(f"Could not save '{task.title}': {exc}") from exc

    @staticmethod
    def _unlink(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise StorageError(f"Could not remove {path}: {exc}") from exc
