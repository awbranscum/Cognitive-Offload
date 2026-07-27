"""Data model.

Everything here is pure Python with no tkinter import, so it can be unit
tested without a display.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def now_stamp() -> str:
    """Current local time in the sortable format used throughout the app."""
    return datetime.now().strftime(TIMESTAMP_FORMAT)


def new_id() -> str:
    return uuid.uuid4().hex


def _as_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _as_str(value, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _as_tags(value) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    tags: list[str] = []
    for tag in value:
        if not isinstance(tag, str):
            continue
        cleaned = tag.strip().lower()
        if cleaned and cleaned not in tags:
            tags.append(cleaned)
    return tags


@dataclass
class Task:
    """A single item on the active stack.

    ``id`` is what the UI uses to map a listbox row back to a task; relying on
    value equality breaks as soon as two tasks share the same text.
    """

    text: str
    done: bool = False
    created_at: str = field(default_factory=now_stamp)
    priority: int = 0
    tags: list[str] = field(default_factory=list)
    completed_at: str | None = None
    description: str = ""
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        self.text = _as_str(self.text).strip()
        self.description = _as_str(self.description)
        self.tags = _as_tags(self.tags)
        self.priority = 1 if self.priority else 0
        self.done = _as_bool(self.done)
        if not self.created_at:
            self.created_at = now_stamp()
        if not self.done:
            self.completed_at = None

    # -- state changes -------------------------------------------------
    def set_done(self, done: bool) -> None:
        self.done = bool(done)
        self.completed_at = now_stamp() if self.done else None

    def toggle_done(self) -> None:
        self.set_done(not self.done)

    def toggle_priority(self) -> None:
        self.priority = 0 if self.priority else 1

    def add_tag(self, tag: str) -> bool:
        cleaned = tag.strip().lower()
        if not cleaned or cleaned in self.tags:
            return False
        self.tags.append(cleaned)
        return True

    def remove_tag(self, tag: str) -> bool:
        cleaned = tag.strip().lower()
        if cleaned not in self.tags:
            return False
        self.tags.remove(cleaned)
        return True

    def matches(self, term: str) -> bool:
        """Case-insensitive search across title, description and tags."""
        term = term.strip().lower()
        if not term:
            return True
        if term in self.text.lower() or term in self.description.lower():
            return True
        return any(term in tag for tag in self.tags)

    # -- serialisation -------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "done": self.done,
            "created_at": self.created_at,
            "priority": self.priority,
            "tags": list(self.tags),
            "completed_at": self.completed_at,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        """Build a task from stored JSON, tolerating older/partial records."""
        if not isinstance(data, dict):
            raise ValueError("task record must be an object")
        completed_at = data.get("completed_at")
        return cls(
            text=_as_str(data.get("text")),
            done=_as_bool(data.get("done")),
            created_at=_as_str(data.get("created_at")),
            priority=1 if data.get("priority") else 0,
            tags=_as_tags(data.get("tags")),
            completed_at=completed_at if isinstance(completed_at, str) else None,
            description=_as_str(data.get("description")),
            id=_as_str(data.get("id")) or new_id(),
        )

    def copy(self) -> "Task":
        return Task.from_dict(self.to_dict())


@dataclass
class Note:
    """A timestamped scratchpad line (kept for reading pre-2.0 save files)."""

    text: str
    created_at: str = field(default_factory=now_stamp)

    def to_dict(self) -> dict:
        return {"text": self.text, "created_at": self.created_at}

    @classmethod
    def from_dict(cls, data: dict) -> "Note":
        return cls(
            text=_as_str(data.get("text")),
            created_at=_as_str(data.get("created_at")) or now_stamp(),
        )

    def render(self) -> str:
        return f"[{self.created_at}] {self.text}" if self.created_at else self.text


@dataclass
class MatrixTask:
    """A task living in one of the four Eisenhower quadrants (one file each)."""

    title: str
    content: str = ""
    category: str = "do_first"
    created_at: str = field(default_factory=now_stamp)
    updated_at: str = field(default_factory=now_stamp)
    id: str = field(default_factory=new_id)
    # Absolute path of the backing file; assigned by the store, never stored.
    path: object = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "category": self.category,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict, category: str = "do_first") -> "MatrixTask":
        return cls(
            title=_as_str(data.get("title")).strip(),
            content=_as_str(data.get("content")),
            category=_as_str(data.get("category")) or category,
            created_at=_as_str(data.get("created_at")) or now_stamp(),
            updated_at=_as_str(data.get("updated_at")) or now_stamp(),
            id=_as_str(data.get("id")) or new_id(),
        )

    def to_task(self) -> Task:
        """Convert back into a main-list task."""
        return Task(text=self.title, description=self.content, created_at=now_stamp())
