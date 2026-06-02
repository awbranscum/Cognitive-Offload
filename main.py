import json
import os
import time
import tkinter as tk
from dataclasses import dataclass, asdict
from datetime import datetime
from tkinter import filedialog, messagebox, simpledialog, ttk

APP_TITLE = "Cognitive Offload Prototype"
DATA_FILE = os.path.join(os.path.expanduser("~"), ".cognitive_offload_prototype.json")

@dataclass
class Task:
    text: str
    done: bool = False
    created_at: str = ""
    priority: int = 0  # 0 = normal, 1 = high
    tags: list = None
    completed_at: str = None
    description: str = ""  # Additional details for the task
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []

@dataclass
class Note:
    text: str
    created_at: str = ""

class CognitiveOffloadApp(tk.Tk):
    """A lightweight prototype for externalizing short-term memory load.
    Features:
    - Quick capture box for stray thoughts
    - Task list with check/uncheck and deletion
    - Scratchpad / working note area
    - Focus timer
    - Persistence to a local JSON file
    """
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("980x680")
        self.minsize(900, 600)
        self.tasks: list[Task] = []
        self.notes: list[Note] = []
        self.timer_running = False
        self.timer_seconds_left = 25 * 60
        self.timer_job = None
        self.current_file = DATA_FILE
        self.tag_filter = None
        self.sort_order = "priority"  # "priority", "created", "completed"
        self._build_style()
        self._build_ui()
        self._bind_shortcuts()
        self._load_state()
        self._refresh_all()
    # ---------- UI ----------
    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#f5f6f8")
        style.configure("Header.TLabel", font=("Helvetica", 18, "bold"), background="#f5f6f8")
        style.configure("Sub.TLabel", font=("Helvetica", 10), background="#f5f6f8", foreground="#555")
        style.configure("TLabel", background="#f5f6f8")
        style.configure("TButton", padding=(10, 6))
        style.configure("Card.TLabelframe", background="#f5f6f8", padding=10)
        style.configure("Card.TLabelframe.Label", background="#f5f6f8", font=("Helvetica", 10, "bold"))
        style.configure("HighPriority.TLabel", foreground="red", font=("Helvetica", 10, "bold"))
    def _build_ui(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)
        # Header
        header = ttk.Frame(root)
        header.pack(fill="x")
        ttk.Label(header, text="Cognitive Offload Prototype", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Use this as a second brain: capture, sort, and keep the active mental stack visible.",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(2, 10))
        # Main layout
        body = ttk.Frame(root)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(1, weight=1)
        # Capture + timer row
        top = ttk.Frame(body)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        top.columnconfigure(0, weight=2)
        top.columnconfigure(1, weight=1)
        capture_card = ttk.Labelframe(top, text="Quick capture", style="Card.TLabelframe")
        capture_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        capture_card.columnconfigure(0, weight=1)
        self.capture_entry = ttk.Entry(capture_card)
        self.capture_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.capture_entry.bind("<Return>", lambda e: self.add_task_from_capture())
        add_btn = ttk.Button(capture_card, text="Add to task list", command=self.add_task_from_capture)
        add_btn.grid(row=0, column=1, padx=(0, 6))
        note_btn = ttk.Button(capture_card, text="Add to scratchpad", command=self.add_note_from_capture)
        note_btn.grid(row=0, column=2)
        timer_card = ttk.Labelframe(top, text="Focus timer", style="Card.TLabelframe")
        timer_card.grid(row=0, column=1, sticky="nsew")
        timer_card.columnconfigure(0, weight=1)
        self.timer_label = ttk.Label(timer_card, text=self._format_timer(), font=("Helvetica", 22, "bold"))
        self.timer_label.grid(row=0, column=0, columnspan=4, pady=(0, 6))
        self.work_minutes = tk.IntVar(value=25)
        ttk.Label(timer_card, text="Minutes:").grid(row=1, column=0, sticky="e")
        ttk.Spinbox(timer_card, from_=5, to=120, textvariable=self.work_minutes, width=6).grid(row=1, column=1, sticky="w")
        ttk.Button(timer_card, text="Start", command=self.start_timer).grid(row=1, column=2, padx=4)
        ttk.Button(timer_card, text="Reset", command=self.reset_timer).grid(row=1, column=3)
        # Left pane: tasks
        tasks_card = ttk.Labelframe(body, text="Tasks / Active stack", style="Card.TLabelframe")
        tasks_card.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        tasks_card.rowconfigure(1, weight=1)
        tasks_card.columnconfigure(0, weight=1)
        task_buttons = ttk.Frame(tasks_card)
        task_buttons.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(task_buttons, text="Mark done", command=self.mark_task_done).pack(side="left", padx=(0, 6))
        ttk.Button(task_buttons, text="Delete", command=self.delete_selected_task).pack(side="left", padx=(0, 6))
        ttk.Button(task_buttons, text="Move to top", command=self.promote_selected_task).pack(side="left")
        ttk.Button(task_buttons, text="High Priority", command=self.toggle_high_priority).pack(side="left", padx=(0, 6))
        ttk.Button(task_buttons, text="Add Tag", command=self.add_tag_to_task).pack(side="left", padx=(0, 6))
        ttk.Button(task_buttons, text="Edit Details", command=self.edit_task_details).pack(side="left", padx=(0, 6))
        # Sorting and filtering
        filter_frame = ttk.Frame(tasks_card)
        filter_frame.grid(row=1, column=0, sticky="ew", pady=(0, 5))
        ttk.Label(filter_frame, text="Filter by tag:").pack(side="left")
        self.tag_filter_var = tk.StringVar()
        self.tag_filter_combo = ttk.Combobox(filter_frame, textvariable=self.tag_filter_var, width=12)
        self.tag_filter_combo.pack(side="left", padx=(5, 5))
        self.tag_filter_combo.bind("<<ComboboxSelected>>", self.apply_tag_filter)
        ttk.Button(filter_frame, text="Clear Filter", command=self.clear_tag_filter).pack(side="left", padx=(0, 10))
        ttk.Label(filter_frame, text="Sort by:").pack(side="left")
        sort_options = ["Priority", "Created", "Completed"]
        self.sort_var = tk.StringVar(value="Priority")
        sort_combo = ttk.Combobox(filter_frame, textvariable=self.sort_var, values=sort_options, width=10, state="readonly")
        sort_combo.pack(side="left", padx=(5, 5))
        sort_combo.bind("<<ComboboxSelected>>", self.apply_sorting)
        self.task_list = tk.Listbox(tasks_card, activestyle="dotbox", height=13)
        self.task_list.grid(row=2, column=0, sticky="nsew")
        task_scroll = ttk.Scrollbar(tasks_card, orient="vertical", command=self.task_list.yview)
        task_scroll.grid(row=2, column=1, sticky="ns")
        self.task_list.configure(yscrollcommand=task_scroll.set)
        self.task_list.bind("<Double-Button-1>", lambda e: self.mark_task_done())
        task_entry_row = ttk.Frame(tasks_card)
        task_entry_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        task_entry_row.columnconfigure(0, weight=1)
        self.task_entry = ttk.Entry(task_entry_row)
        self.task_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.task_entry.bind("<Return>", lambda e: self.add_task_direct())
        ttk.Button(task_entry_row, text="Add task", command=self.add_task_direct).grid(row=0, column=1)
        # Right pane: scratchpad
        notes_card = ttk.Labelframe(body, text="Scratchpad / Working note", style="Card.TLabelframe")
        notes_card.grid(row=1, column=1, sticky="nsew")
        notes_card.rowconfigure(1, weight=1)
        notes_card.columnconfigure(0, weight=1)
        note_buttons = ttk.Frame(notes_card)
        note_buttons.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(note_buttons, text="Copy last note to task", command=self.copy_last_note_to_task).pack(side="left", padx=(0, 6))
        ttk.Button(note_buttons, text="Clear scratchpad", command=self.clear_notes).pack(side="left")
        self.note_text = tk.Text(notes_card, wrap="word", height=18, undo=True)
        self.note_text.grid(row=1, column=0, sticky="nsew")
        note_scroll = ttk.Scrollbar(notes_card, orient="vertical", command=self.note_text.yview)
        note_scroll.grid(row=1, column=1, sticky="ns")
        self.note_text.configure(yscrollcommand=note_scroll.set)
        footer = ttk.Frame(root)
        footer.pack(fill="x", pady=(10, 0))
        ttk.Button(footer, text="Save", command=self.save_state).pack(side="left", padx=(0, 6))
        ttk.Button(footer, text="Load", command=self.load_state_dialog).pack(side="left", padx=(0, 6))
        ttk.Button(footer, text="Export JSON", command=self.export_state).pack(side="left", padx=(0, 6))
        ttk.Button(footer, text="Brain dump into tasks", command=self.brain_dump_into_tasks).pack(side="left")
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(footer, textvariable=self.status_var, style="Sub.TLabel").pack(side="right")
    def _bind_shortcuts(self):
        self.bind_all("<Control-s>", lambda e: self.save_state())
        self.bind_all("<Control-n>", lambda e: self.add_task_direct())
        self.bind_all("<Control-Shift-S>", lambda e: self.add_note_from_capture())
        self.bind_all("<Control-Return>", lambda e: self.add_task_from_capture())
        self.bind_all("<Escape>", lambda e: self.stop_timer())
        self.bind_all("<Control-p>", lambda e: self.toggle_high_priority())
        self.bind_all("<Control-t>", lambda e: self.add_tag_to_task())
        self.bind_all("<Control-d>", lambda e: self.edit_task_details())
    # ---------- Helpers ----------
    def _timestamp(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    def _set_status(self, msg: str):
        self.status_var.set(msg)
    def _format_timer(self) -> str:
        m, s = divmod(max(0, self.timer_seconds_left), 60)
        return f"{m:02d}:{s:02d}"
    def _selected_task_index(self):
        sel = self.task_list.curselection()
        if not sel:
            return None
        return sel[0]
    def _refresh_all(self):
        self._refresh_tasks()
        self._refresh_notes()
        self._refresh_tag_filter()
        self.timer_label.config(text=self._format_timer())
    def _refresh_tasks(self):
        self.task_list.delete(0, tk.END)
        display_tasks = self.tasks
        
        # Apply tag filter
        if self.tag_filter:
            display_tasks = [t for t in self.tasks if self.tag_filter in t.tags]
            
        # Apply sorting
        if self.sort_order == "priority":
            # High priority first, then by creation date (newest first)
            display_tasks = sorted(display_tasks, key=lambda t: (-t.priority, t.created_at), reverse=True)
        elif self.sort_order == "created":
            # By creation date (newest first)
            display_tasks = sorted(display_tasks, key=lambda t: t.created_at, reverse=True)
        elif self.sort_order == "completed":
            # Completed tasks first, then by completion date (newest first)
            display_tasks = sorted(display_tasks, key=lambda t: (not t.done, t.completed_at or "9999"), reverse=True)
            
        for t in display_tasks:
            prefix = "✓" if t.done else "•"
            priority_marker = "❗" if t.priority == 1 else ""
            tag_marker = f"[{', '.join(t.tags)}]" if t.tags else ""
            desc_marker = " ⓘ" if t.description.strip() else ""
            time_marker = f" ({t.completed_at})" if t.done and t.completed_at else ""
            display_text = f"{priority_marker}{prefix} {t.text} {tag_marker}{desc_marker}{time_marker}"
            self.task_list.insert(tk.END, display_text)
            # Color high priority tasks
            if t.priority == 1 and not t.done:
                self.task_list.itemconfig(tk.END, {'fg': 'red'})
            # Color done tasks
            elif t.done:
                self.task_list.itemconfig(tk.END, {'fg': 'gray'})
    def _refresh_notes(self):
        # Preserve current text if the user is editing, but ensure startup/load shows latest notes.
        if not self.note_text.edit_modified():
            self.note_text.delete("1.0", tk.END)
            if self.notes:
                combined = "\n".join(f"[{n.created_at}] {n.text}" for n in self.notes)
                self.note_text.insert("1.0", combined)
            self.note_text.edit_modified(False)
    def _refresh_tag_filter(self):
        # Get all unique tags
        all_tags = set()
        for task in self.tasks:
            all_tags.update(task.tags)
        tags_list = sorted(list(all_tags))
        self.tag_filter_combo['values'] = tags_list
    # ---------- Actions ----------
    def add_task_from_capture(self):
        text = self.capture_entry.get().strip()
        if not text:
            return
        self.tasks.insert(0, Task(text=text, done=False, created_at=self._timestamp()))
        self.capture_entry.delete(0, tk.END)
        self._refresh_all()
        self._set_status("Captured as task.")
    def add_note_from_capture(self):
        text = self.capture_entry.get().strip()
        if not text:
            return
        self.notes.append(Note(text=text, created_at=self._timestamp()))
        self.capture_entry.delete(0, tk.END)
        self._refresh_notes()
        self._set_status("Captured in scratchpad.")
    def add_task_direct(self):
        text = self.task_entry.get().strip()
        if not text:
            return
        self.tasks.insert(0, Task(text=text, done=False, created_at=self._timestamp()))
        self.task_entry.delete(0, tk.END)
        self._refresh_all()
        self._set_status("Task added.")
    def mark_task_done(self):
        idx = self._selected_task_index()
        if idx is None:
            return
            
        # Find the actual task based on current display order
        display_tasks = self.tasks
        if self.tag_filter:
            display_tasks = [t for t in self.tasks if self.tag_filter in t.tags]
            
        if self.sort_order == "priority":
            display_tasks = sorted(display_tasks, key=lambda t: (-t.priority, t.created_at), reverse=True)
        elif self.sort_order == "created":
            display_tasks = sorted(display_tasks, key=lambda t: t.created_at, reverse=True)
        elif self.sort_order == "completed":
            display_tasks = sorted(display_tasks, key=lambda t: (not t.done, t.completed_at or "9999"), reverse=True)
            
        if idx < len(display_tasks):
            task = display_tasks[idx]
            actual_idx = self.tasks.index(task)
            self.tasks[actual_idx].done = not self.tasks[actual_idx].done
            if self.tasks[actual_idx].done:
                self.tasks[actual_idx].completed_at = self._timestamp()
            else:
                self.tasks[actual_idx].completed_at = None
            self._refresh_all()
            self.task_list.selection_set(idx)
            self._set_status("Toggled task completion.")
    def delete_selected_task(self):
        idx = self._selected_task_index()
        if idx is None:
            return
            
        # Find the actual task based on current display order
        display_tasks = self.tasks
        if self.tag_filter:
            display_tasks = [t for t in self.tasks if self.tag_filter in t.tags]
            
        if self.sort_order == "priority":
            display_tasks = sorted(display_tasks, key=lambda t: (-t.priority, t.created_at), reverse=True)
        elif self.sort_order == "created":
            display_tasks = sorted(display_tasks, key=lambda t: t.created_at, reverse=True)
        elif self.sort_order == "completed":
            display_tasks = sorted(display_tasks, key=lambda t: (not t.done, t.completed_at or "9999"), reverse=True)
            
        if idx < len(display_tasks):
            task = display_tasks[idx]
            actual_idx = self.tasks.index(task)
            del self.tasks[actual_idx]
            self._refresh_all()
            self._set_status("Task deleted.")
    def promote_selected_task(self):
        idx = self._selected_task_index()
        if idx is None:
            return
            
        # Find the actual task based on current display order
        display_tasks = self.tasks
        if self.tag_filter:
            display_tasks = [t for t in self.tasks if self.tag_filter in t.tags]
            
        if self.sort_order == "priority":
            display_tasks = sorted(display_tasks, key=lambda t: (-t.priority, t.created_at), reverse=True)
        elif self.sort_order == "created":
            display_tasks = sorted(display_tasks, key=lambda t: t.created_at, reverse=True)
        elif self.sort_order == "completed":
            display_tasks = sorted(display_tasks, key=lambda t: (not t.done, t.completed_at or "9999"), reverse=True)
            
        if idx < len(display_tasks):
            task = display_tasks[idx]
            actual_idx = self.tasks.index(task)
            if actual_idx == 0:
                return
            task_obj = self.tasks.pop(actual_idx)
            self.tasks.insert(0, task_obj)
            self._refresh_all()
            self.task_list.selection_set(0)
            self._set_status("Task moved to top.")
    def toggle_high_priority(self):
        idx = self._selected_task_index()
        if idx is None:
            return
            
        # Find the actual task based on current display order
        display_tasks = self.tasks
        if self.tag_filter:
            display_tasks = [t for t in self.tasks if self.tag_filter in t.tags]
            
        if self.sort_order == "priority":
            display_tasks = sorted(display_tasks, key=lambda t: (-t.priority, t.created_at), reverse=True)
        elif self.sort_order == "created":
            display_tasks = sorted(display_tasks, key=lambda t: t.created_at, reverse=True)
        elif self.sort_order == "completed":
            display_tasks = sorted(display_tasks, key=lambda t: (not t.done, t.completed_at or "9999"), reverse=True)
            
        if idx < len(display_tasks):
            task = display_tasks[idx]
            actual_idx = self.tasks.index(task)
            self.tasks[actual_idx].priority = 1 - self.tasks[actual_idx].priority
            self._refresh_all()
            self.task_list.selection_set(idx)
            self._set_status("Toggled high priority.")
    def add_tag_to_task(self):
        idx = self._selected_task_index()
        if idx is None:
            return
            
        # Find the actual task based on current display order
        display_tasks = self.tasks
        if self.tag_filter:
            display_tasks = [t for t in self.tasks if self.tag_filter in t.tags]
            
        if self.sort_order == "priority":
            display_tasks = sorted(display_tasks, key=lambda t: (-t.priority, t.created_at), reverse=True)
        elif self.sort_order == "created":
            display_tasks = sorted(display_tasks, key=lambda t: t.created_at, reverse=True)
        elif self.sort_order == "completed":
            display_tasks = sorted(display_tasks, key=lambda t: (not t.done, t.completed_at or "9999"), reverse=True)
            
        if idx < len(display_tasks):
            task = display_tasks[idx]
            actual_idx = self.tasks.index(task)
            tag = simpledialog.askstring("Add Tag", "Enter tag name:")
            if tag:
                tag = tag.strip().lower()
                if tag and tag not in self.tasks[actual_idx].tags:
                    self.tasks[actual_idx].tags.append(tag)
                    self._refresh_all()
                    self._set_status(f"Added tag '{tag}' to task.")
    def edit_task_details(self):
        idx = self._selected_task_index()
        if idx is None:
            return
            
        # Find the actual task based on current display order
        display_tasks = self.tasks
        if self.tag_filter:
            display_tasks = [t for t in self.tasks if self.tag_filter in t.tags]
            
        if self.sort_order == "priority":
            display_tasks = sorted(display_tasks, key=lambda t: (-t.priority, t.created_at), reverse=True)
        elif self.sort_order == "created":
            display_tasks = sorted(display_tasks, key=lambda t: t.created_at, reverse=True)
        elif self.sort_order == "completed":
            display_tasks = sorted(display_tasks, key=lambda t: (not t.done, t.completed_at or "9999"), reverse=True)
            
        if idx < len(display_tasks):
            task = display_tasks[idx]
            actual_idx = self.tasks.index(task)
            
            # Create a dialog for editing task details
            dialog = tk.Toplevel(self)
            dialog.title("Edit Task Details")
            dialog.geometry("400x300")
            dialog.transient(self)
            dialog.grab_set()
            
            # Task text
            ttk.Label(dialog, text="Task:").pack(anchor="w", padx=10, pady=(10, 0))
            task_text = tk.Text(dialog, height=3, wrap="word")
            task_text.pack(fill="x", padx=10, pady=(0, 10))
            task_text.insert("1.0", self.tasks[actual_idx].text)
            
            # Description
            ttk.Label(dialog, text="Description:").pack(anchor="w", padx=10, pady=(0, 0))
            desc_text = tk.Text(dialog, height=8, wrap="word")
            desc_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            desc_text.insert("1.0", self.tasks[actual_idx].description)
            
            # Buttons
            button_frame = ttk.Frame(dialog)
            button_frame.pack(fill="x", padx=10, pady=(0, 10))
            
            def save_changes():
                new_text = task_text.get("1.0", tk.END).strip()
                new_desc = desc_text.get("1.0", tk.END).strip()
                if new_text:
                    self.tasks[actual_idx].text = new_text
                self.tasks[actual_idx].description = new_desc
                self._refresh_all()
                self._set_status("Task details updated.")
                dialog.destroy()
            
            ttk.Button(button_frame, text="Save", command=save_changes).pack(side="right", padx=5)
            ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side="right")
            
            # Center the dialog
            dialog.update_idletasks()
            x = self.winfo_x() + self.winfo_width() // 2 - dialog.winfo_width() // 2
            y = self.winfo_y() + self.winfo_height() // 2 - dialog.winfo_height() // 2
            dialog.geometry(f"+{x}+{y}")
    def apply_tag_filter(self, event=None):
        self.tag_filter = self.tag_filter_var.get()
        self._refresh_tasks()
    def clear_tag_filter(self):
        self.tag_filter = None
        self.tag_filter_var.set('')
        self._refresh_tasks()
    def apply_sorting(self, event=None):
        sort_value = self.sort_var.get()
        if sort_value == "Priority":
            self.sort_order = "priority"
        elif sort_value == "Created":
            self.sort_order = "created"
        elif sort_value == "Completed":
            self.sort_order = "completed"
        self._refresh_tasks()
    def copy_last_note_to_task(self):
        if not self.notes:
            return
        text = self.notes[-1].text.strip()
        if not text:
            return
        self.tasks.insert(0, Task(text=text, done=False, created_at=self._timestamp()))
        self._refresh_all()
        self._set_status("Last note copied to task list.")
    def clear_notes(self):
        if not messagebox.askyesno("Clear scratchpad", "Clear all notes from the scratchpad?"):
            return
        self.notes.clear()
        self.note_text.delete("1.0", tk.END)
        self._set_status("Scratchpad cleared.")
    def brain_dump_into_tasks(self):
        raw = self.note_text.get("1.0", tk.END).strip()
        if not raw:
            return
        lines = [line.strip("-• \t") for line in raw.splitlines() if line.strip()]
        for line in lines:
            self.tasks.insert(0, Task(text=line, done=False, created_at=self._timestamp()))
        self._refresh_all()
        self._set_status(f"Moved {len(lines)} line(s) into tasks.")
    # ---------- Timer ----------
    def start_timer(self):
        if self.timer_running:
            return
        self.timer_seconds_left = int(self.work_minutes.get()) * 60
        self.timer_running = True
        self._tick_timer()
        self._set_status("Timer started.")
    def _tick_timer(self):
        if not self.timer_running:
            return
        self.timer_label.config(text=self._format_timer())
        if self.timer_seconds_left <= 0:
            self.timer_running = False
            self.bell()
            messagebox.showinfo("Focus timer", "Timer finished. Take a break.")
            self._set_status("Timer finished.")
            return
        self.timer_seconds_left -= 1
        self.timer_job = self.after(1000, self._tick_timer)
    def stop_timer(self):
        if self.timer_job is not None:
            self.after_cancel(self.timer_job)
            self.timer_job = None
        self.timer_running = False
        self._set_status("Timer stopped.")
    def reset_timer(self):
        self.stop_timer()
        self.timer_seconds_left = int(self.work_minutes.get()) * 60
        self.timer_label.config(text=self._format_timer())
        self._set_status("Timer reset.")
    # ---------- Persistence ----------
    def to_dict(self):
        return {
            "tasks": [asdict(t) for t in self.tasks],
            "notes": [asdict(n) for n in self.notes],
            "timer_minutes": int(self.work_minutes.get()),
            "saved_at": self._timestamp(),
        }
    def from_dict(self, data):
        self.tasks = []
        for t_data in data.get("tasks", []):
            # Handle missing fields for backward compatibility
            if "priority" not in t_data:
                t_data["priority"] = 0
            if "tags" not in t_data:
                t_data["tags"] = []
            if "completed_at" not in t_data:
                t_data["completed_at"] = None
            if "description" not in t_data:
                t_data["description"] = ""
            self.tasks.append(Task(**t_data))
        self.notes = [Note(**n) for n in data.get("notes", [])]
        try:
            self.work_minutes.set(int(data.get("timer_minutes", 25)))
        except Exception:
            self.work_minutes.set(25)
        self.timer_seconds_left = int(self.work_minutes.get()) * 60
        self.timer_label.config(text=self._format_timer())
    def save_state(self):
        try:
            with open(self.current_file, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            self._set_status(f"Saved to {self.current_file}")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))
    def load_state(self):
        if not os.path.exists(self.current_file):
            return
        try:
            with open(self.current_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.from_dict(data)
            self._refresh_all()
            self._set_status(f"Loaded from {self.current_file}")
        except Exception as e:
            messagebox.showerror("Load failed", str(e))
    def _load_state(self):
        self.load_state()
    def load_state_dialog(self):
        path = filedialog.askopenfilename(
            title="Load state",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.from_dict(data)
            self._refresh_all()
            self._set_status(f"Loaded {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Load failed", str(e))
    def export_state(self):
        path = filedialog.asksaveasfilename(
            title="Export state as JSON",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            self._set_status(f"Exported to {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))
    # ---------- Close ----------
    def on_close(self):
        try:
            self.save_state()
        finally:
            self.destroy()

if __name__ == "__main__":
    app = CognitiveOffloadApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()