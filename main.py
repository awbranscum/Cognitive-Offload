# File: main.py
import json
import os
import time
import tkinter as tk
from dataclasses import dataclass, asdict
from datetime import datetime
from tkinter import filedialog, messagebox, simpledialog, ttk
from pathlib import Path

APP_TITLE = "Cognitive Offload Prototype"
DEFAULT_DB_PATH = Path.home() / ".cognitive_offload"

@dataclass
class Task:
    text: str
    done: bool = False
    created_at: str = ""
    priority: int = 0
    tags: list = None
    completed_at: str = None
    description: str = ""
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []

@dataclass
class Note:
    text: str
    created_at: str = ""

class TaskDialog:
    def __init__(self, parent, category, title="", content=""):
        self.window = tk.Toplevel(parent)
        self.window.title(f"{'Edit' if title else 'Add'} Task ({category.replace('_', ' ').title()})")
        self.window.geometry("400x300")
        self.window.transient(parent)
        self.window.grab_set()
        self.result = None
        
        ttk.Label(self.window, text="Task Title:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        self.title_entry = ttk.Entry(self.window)
        self.title_entry.pack(fill=tk.X, padx=10, pady=(0, 10))
        self.title_entry.insert(0, title)
        
        ttk.Label(self.window, text="Content:").pack(anchor=tk.W, padx=10)
        self.content_text = tk.Text(self.window, height=10)
        self.content_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.content_text.insert("1.0", content)
        
        btn_frame = ttk.Frame(self.window)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Button(btn_frame, text="OK", command=self.ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.window.destroy).pack(side=tk.RIGHT)
    
    def ok(self):
        title = self.title_entry.get().strip()
        content = self.content_text.get("1.0", tk.END).strip()
        if not title:
            messagebox.showerror("Error", "Task title cannot be empty")
            return
        self.result = (title, content)
        self.window.destroy()

class MatrixSelectionDialog:
    def __init__(self, parent, multiple=False, title="Select Matrix Quadrant"):
        self.window = tk.Toplevel(parent)
        self.window.title(title)
        self.window.geometry("300x180")
        self.window.transient(parent)
        self.window.grab_set()
        self.result = None
        self.multiple = multiple
        
        ttk.Label(self.window, text="Select Matrix Quadrant:", font=("Helvetica", 10, "bold")).pack(pady=10)
        
        frame = ttk.Frame(self.window)
        frame.pack(fill="x", padx=20)
        
        quadrants = [
            ("Do First (Urgent/Important)", "do_first"),
            ("Schedule (Not Urgent/Important)", "schedule"),
            ("Delegate (Urgent/Not Important)", "delegate"),
            ("Eliminate (Not Urgent/Not Important)", "eliminate")
        ]
        
        self.selected_quadrant = tk.StringVar(value="do_first")
        
        for text, value in quadrants:
            ttk.Radiobutton(frame, text=text, variable=self.selected_quadrant, value=value).pack(anchor="w", pady=2)
        
        button_frame = ttk.Frame(self.window)
        button_frame.pack(pady=15)
        action_text = "Move Task(s)" if multiple else "Move Task"
        ttk.Button(button_frame, text=action_text, command=self.ok).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.window.destroy).pack(side="left", padx=5)
    
    def ok(self):
        self.result = self.selected_quadrant.get()
        self.window.destroy()

class CognitiveOffloadApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1000x700")
        self.minsize(900, 600)
        self.tasks: list[Task] = []
        self.notes: list[Note] = []
        self.timer_running = False
        self.timer_seconds_left = 25 * 60
        self.timer_job = None
        self.db_path = DEFAULT_DB_PATH
        self.current_file = self.db_path / "data.json"
        self.tag_filter = None
        self.sort_order = "priority"
        self.auto_save_enabled = True
        self.last_auto_save = time.time()
        self.auto_save_interval = 30
        self.search_var = tk.StringVar()
        self.matrix_db_path = Path.home() / "MatrixTasks"
        self.load_config()
        self.ensure_db_structure()
        self.ensure_matrix_structure()
        self._build_style()
        self._build_ui()
        self._bind_shortcuts()
        self._load_state()
        self._refresh_all()
        self._start_auto_save()
    
    def load_config(self):
        config_file = Path.home() / ".cognitive_offload_config.json"
        try:
            with open(config_file, "r") as f:
                config = json.load(f)
                self.db_path = Path(config.get("db_path", str(DEFAULT_DB_PATH)))
                self.current_file = self.db_path / "data.json"
                self.matrix_db_path = Path(config.get("matrix_db_path", str(self.matrix_db_path)))
        except FileNotFoundError:
            self.save_config()
    
    def save_config(self):
        config_file = Path.home() / ".cognitive_offload_config.json"
        config = {
            "db_path": str(self.db_path),
            "matrix_db_path": str(self.matrix_db_path)
        }
        with open(config_file, "w") as f:
            json.dump(config, f)
    
    def ensure_db_structure(self):
        self.db_path.mkdir(parents=True, exist_ok=True)
    
    def ensure_matrix_structure(self):
        categories = ["do_first", "schedule", "delegate", "eliminate"]
        category_names = ["DoFirst", "Schedule", "Delegate", "Eliminate"]
        
        self.category_paths = {}
        for cat, name in zip(categories, category_names):
            path = self.matrix_db_path / name
            path.mkdir(parents=True, exist_ok=True)
            self.category_paths[cat] = path
    
    def change_db_folder(self):
        new_path = filedialog.askdirectory(initialdir=str(self.db_path))
        if new_path:
            self.db_path = Path(new_path)
            self.current_file = self.db_path / "data.json"
            self.save_config()
            self.ensure_db_structure()
            self._load_state()
            self._refresh_all()
            self._set_status(f"Database changed to {self.db_path}")
    
    def change_matrix_db_folder(self):
        new_path = filedialog.askdirectory(initialdir=str(self.matrix_db_path))
        if new_path:
            self.matrix_db_path = Path(new_path)
            self.save_config()
            self.ensure_matrix_structure()
            self.refresh_matrix_task_list()
            self._set_status(f"Matrix database changed to {self.matrix_db_path}")

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
        style.configure("Search.TEntry", foreground="#666")
        style.configure("Matrix.TLabelframe", background="#e8f4f8", padding=10)
        style.configure("MatrixHeader.TLabel", font=("Helvetica", 14, "bold"), background="#e8f4f8")

    def _build_ui(self):
        main_container = ttk.Frame(self)
        main_container.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.notebook = ttk.Notebook(main_container)
        self.notebook.pack(fill="both", expand=True)
        
        self.main_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.main_frame, text="🧠 Cognitive Offload")
        self._build_main_ui()
        
        self.matrix_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.matrix_frame, text="📋 Eisenhower Matrix")
        self._build_matrix_ui()
    
    def _build_main_ui(self):
        root = self.main_frame
        
        header = ttk.Frame(root)
        header.pack(fill="x", padx=10, pady=5)
        ttk.Label(header, text="Cognitive Offload Prototype", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Use this as a second brain: capture, sort, and keep the active mental stack visible.",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(2, 10))
        
        db_frame = ttk.Frame(header)
        db_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(db_frame, text="Database:").pack(side="left")
        self.path_label = ttk.Label(db_frame, text=str(self.db_path), foreground="#0066cc")
        self.path_label.pack(side="left", padx=(5, 10))
        ttk.Button(db_frame, text="Change", command=self.change_db_folder).pack(side="left")
        
        body = ttk.Frame(root)
        body.pack(fill="both", expand=True, padx=10, pady=5)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(1, weight=1)
        
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
        self.capture_entry.bind("<Control-Return>", lambda e: self.add_note_from_capture())
        
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
        
        tasks_card = ttk.Labelframe(body, text="Tasks / Active stack", style="Card.TLabelframe")
        tasks_card.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        tasks_card.rowconfigure(2, weight=1)
        tasks_card.columnconfigure(0, weight=1)
        
        search_frame = ttk.Frame(tasks_card)
        search_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(search_frame, text="🔍").pack(side="left", padx=(0, 5))
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side="left", fill="x", expand=True)
        search_entry.bind("<KeyRelease>", self._on_search_change)
        ttk.Button(search_frame, text="Clear", command=self._clear_search).pack(side="left", padx=(5, 0))
        
        task_buttons = ttk.Frame(tasks_card)
        task_buttons.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(task_buttons, text="Mark done", command=self.mark_task_done).pack(side="left", padx=(0, 6))
        ttk.Button(task_buttons, text="Delete", command=self.delete_selected_task).pack(side="left", padx=(0, 6))
        ttk.Button(task_buttons, text="Move to top", command=self.promote_selected_task).pack(side="left")
        ttk.Button(task_buttons, text="High Priority", command=self.toggle_high_priority).pack(side="left", padx=(0, 6))
        ttk.Button(task_buttons, text="Add Tag", command=self.add_tag_to_task).pack(side="left", padx=(0, 6))
        ttk.Button(task_buttons, text="Edit Details", command=self.edit_task_details).pack(side="left", padx=(0, 6))
        ttk.Button(task_buttons, text="To Matrix", command=self.move_to_matrix).pack(side="left", padx=(0, 6))
        ttk.Button(task_buttons, text="Batch to Matrix", command=self.move_selected_tasks_to_matrix).pack(side="left", padx=(0, 6))
        
        filter_frame = ttk.Frame(tasks_card)
        filter_frame.grid(row=2, column=0, sticky="ew", pady=(0, 5))
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
        
        self.task_list = tk.Listbox(tasks_card, activestyle="dotbox", height=13, selectmode=tk.EXTENDED)
        self.task_list.grid(row=3, column=0, sticky="nsew")
        task_scroll = ttk.Scrollbar(tasks_card, orient="vertical", command=self.task_list.yview)
        task_scroll.grid(row=3, column=1, sticky="ns")
        self.task_list.configure(yscrollcommand=task_scroll.set)
        self.task_list.bind("<Double-Button-1>", lambda e: self.mark_task_done())
        self.task_list.bind("<Delete>", lambda e: self.delete_selected_task())
        self.task_list.bind("<Control-p>", lambda e: self.toggle_high_priority())
        self.task_list.bind("<Control-t>", lambda e: self.add_tag_to_task())
        self.task_list.bind("<Control-d>", lambda e: self.edit_task_details())
        self.task_list.bind("<Up>", self._on_task_list_navigation)
        self.task_list.bind("<Down>", self._on_task_list_navigation)
        
        task_entry_row = ttk.Frame(tasks_card)
        task_entry_row.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        task_entry_row.columnconfigure(0, weight=1)
        self.task_entry = ttk.Entry(task_entry_row)
        self.task_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.task_entry.bind("<Return>", lambda e: self.add_task_direct())
        ttk.Button(task_entry_row, text="Add task", command=self.add_task_direct).grid(row=0, column=1)
        
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
        self.note_text.bind("<Control-Return>", lambda e: self.add_note_from_capture())
        
        footer = ttk.Frame(root)
        footer.pack(fill="x", padx=10, pady=(10, 5))
        ttk.Button(footer, text="Save", command=self.save_state).pack(side="left", padx=(0, 6))
        ttk.Button(footer, text="Load", command=self.load_state_dialog).pack(side="left", padx=(0, 6))
        ttk.Button(footer, text="Export JSON", command=self.export_state).pack(side="left", padx=(0, 6))
        ttk.Button(footer, text="Brain dump into tasks", command=self.brain_dump_into_tasks).pack(side="left")
        
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(footer, textvariable=self.status_var, style="Sub.TLabel").pack(side="right")

    def _build_matrix_ui(self):
        from matrix_ui import build_matrix_ui
        build_matrix_ui(self)

    def _bind_shortcuts(self):
        self.bind_all("<Control-s>", lambda e: self.save_state())
        self.bind_all("<Control-n>", lambda e: self.add_task_direct())
        self.bind_all("<Control-Shift-S>", lambda e: self.add_note_from_capture())
        self.bind_all("<Control-Return>", lambda e: self.add_task_from_capture())
        self.bind_all("<Escape>", lambda e: self.stop_timer())
        self.bind_all("<Control-p>", lambda e: self.toggle_high_priority())
        self.bind_all("<Control-t>", lambda e: self.add_tag_to_task())
        self.bind_all("<Control-d>", lambda e: self.edit_task_details())
        self.bind_all("<Control-b>", lambda e: self.brain_dump_into_tasks())
        self.bind_all("<Control-l>", lambda e: self.load_state_dialog())
        self.bind_all("<Control-f>", lambda e: self.focus_search())
        self.bind_all("<Control-m>", lambda e: self.notebook.select(1))
        self.bind_all("<Control-1>", lambda e: self.notebook.select(0))
        self.bind_all("<Control-2>", lambda e: self.notebook.select(1))
        self.bind_all("<Control-Shift-B>", lambda e: self.move_selected_tasks_to_matrix())

    def focus_search(self):
        self.search_var.set("")
        for child in self.winfo_children():
            if isinstance(child, ttk.Frame):
                for subchild in child.winfo_children():
                    if isinstance(subchild, ttk.Notebook):
                        current_tab = subchild.select()
                        for tab in current_tab.winfo_children():
                            if isinstance(tab, ttk.Labelframe):
                                for subwidget in tab.winfo_children():
                                    if isinstance(subwidget, ttk.Frame):
                                        for entry in subwidget.winfo_children():
                                            if isinstance(entry, ttk.Entry) and hasattr(entry, 'cget') and entry.cget("textvariable") == str(self.search_var):
                                                entry.focus_set()
                                                return

    def _timestamp(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _set_status(self, msg: str):
        self.status_var.set(msg)
        self.after(5000, lambda: self.status_var.set("Ready.") if self.status_var.get() == msg else None)

    def _format_timer(self) -> str:
        m, s = divmod(max(0, self.timer_seconds_left), 60)
        return f"{m:02d}:{s:02d}"

    def _selected_task_index(self):
        sel = self.task_list.curselection()
        if not sel:
            return None
        return sel[0] if len(sel) == 1 else sel

    def _get_display_tasks(self):
        """Get currently displayed tasks accounting for filters and sorting"""
        display_tasks = self.tasks
        
        search_term = self.search_var.get().lower().strip()
        if search_term:
            display_tasks = [t for t in display_tasks if search_term in t.text.lower() or 
                            search_term in t.description.lower() or
                            any(search_term in tag for tag in t.tags)]
        
        if self.tag_filter:
            display_tasks = [t for t in display_tasks if self.tag_filter in t.tags]
            
        if self.sort_order == "priority":
            display_tasks = sorted(display_tasks, key=lambda t: (-t.priority, t.created_at), reverse=True)
        elif self.sort_order == "created":
            display_tasks = sorted(display_tasks, key=lambda t: t.created_at, reverse=True)
        elif self.sort_order == "completed":
            display_tasks = sorted(display_tasks, key=lambda t: (not t.done, t.completed_at or "9999"), reverse=True)
            
        return display_tasks

    def _refresh_all(self):
        self._refresh_tasks()
        self._refresh_notes()
        self._refresh_tag_filter()
        self.timer_label.config(text=self._format_timer())
        self.path_label.config(text=str(self.db_path))
        self.matrix_path_label.config(text=str(self.matrix_db_path))

    def _refresh_tasks(self):
        self.task_list.delete(0, tk.END)
        display_tasks = self._get_display_tasks()
            
        for t in display_tasks:
            prefix = "✓" if t.done else "•"
            priority_marker = "❗" if t.priority == 1 else ""
            tag_marker = f"[{', '.join(t.tags)}]" if t.tags else ""
            desc_marker = " ⓘ" if t.description.strip() else ""
            time_marker = f" ({t.completed_at})" if t.done and t.completed_at else ""
            display_text = f"{priority_marker}{prefix} {t.text} {tag_marker}{desc_marker}{time_marker}"
            self.task_list.insert(tk.END, display_text)
            if t.priority == 1 and not t.done:
                self.task_list.itemconfig(tk.END, {'fg': 'red'})
            elif t.done:
                self.task_list.itemconfig(tk.END, {'fg': 'gray'})

    def _refresh_notes(self):
        if not self.note_text.edit_modified():
            self.note_text.delete("1.0", tk.END)
            if self.notes:
                combined = "\n".join(f"[{n.created_at}] {n.text}" for n in self.notes)
                self.note_text.insert("1.0", combined)
            self.note_text.edit_modified(False)

    def _refresh_tag_filter(self):
        all_tags = set()
        for task in self.tasks:
            all_tags.update(task.tags)
        tags_list = sorted(list(all_tags))
        self.tag_filter_combo['values'] = tags_list

    def _on_task_list_navigation(self, event):
        self.after(100, self._show_selected_task_details)

    def _show_selected_task_details(self):
        sel = self.task_list.curselection()
        if sel:
            idx = sel[0] if len(sel) == 1 else sel[0]
            display_tasks = self._get_display_tasks()
            
            if idx < len(display_tasks):
                task = display_tasks[idx]
                details = f"Task: {task.text}"
                if task.description:
                    details += f" | Description: {task.description[:50]}..."
                if task.tags:
                    details += f" | Tags: {', '.join(task.tags)}"
                self._set_status(details)

    def _on_search_change(self, event=None):
        self._refresh_tasks()

    def _clear_search(self):
        self.search_var.set("")
        self._refresh_tasks()

    def get_category_path(self, category):
        category_names = {
            "do_first": "DoFirst",
            "schedule": "Schedule", 
            "delegate": "Delegate",
            "eliminate": "Eliminate"
        }
        return self.matrix_db_path / category_names[category]
    
    def refresh_matrix_task_list(self):
        categories = ["do_first", "schedule", "delegate", "eliminate"]
        for cat in categories:
            listbox = self.matrix_task_lists[cat]
            listbox.delete(0, tk.END)
            cat_path = self.get_category_path(cat)
            if cat_path.exists():
                for filepath in sorted(cat_path.glob("*.task")):
                    try:
                        with open(filepath, "r") as f:
                            data = json.load(f)
                            listbox.insert(tk.END, data.get("title", filepath.stem))
                    except:
                        listbox.insert(tk.END, filepath.stem)
    
    def sanitize_filename(self, name):
        return "".join(c for c in name if c.isalnum() or c in (' ','.','_','-')).rstrip()
    
    def add_matrix_task(self, category):
        dialog = TaskDialog(self, category)
        self.wait_window(dialog.window)
        if dialog.result:
            title, content = dialog.result
            filename = f"{self.sanitize_filename(title)}.task"
            filepath = self.get_category_path(category) / filename
            
            counter = 1
            base_name = title
            while filepath.exists():
                title = f"{base_name}_{counter}"
                filename = f"{self.sanitize_filename(title)}.task"
                filepath = self.get_category_path(category) / filename
                counter += 1
            
            task_data = {"title": title, "content": content}
            with open(filepath, "w") as f:
                json.dump(task_data, f)
            
            self.refresh_matrix_task_list()
    
    def edit_matrix_task(self, category):
        listbox = self.matrix_task_lists[category]
        selection = listbox.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a task to edit")
            return
        
        task_title = listbox.get(selection[0])
        filepath = self.get_category_path(category) / f"{self.sanitize_filename(task_title)}.task"
        
        if not filepath.exists():
            messagebox.showerror("Error", "Task file not found")
            return
        
        try:
            with open(filepath, "r") as f:
                task_data = json.load(f)
        except:
            with open(filepath, "r") as f:
                content = f.read()
            task_data = {"title": task_title, "content": content}
        
        dialog = TaskDialog(self, category, task_data["title"], task_data["content"])
        self.wait_window(dialog.window)
        if dialog.result:
            new_title, new_content = dialog.result
            
            if new_title != task_data["title"]:
                new_filepath = self.get_category_path(category) / f"{self.sanitize_filename(new_title)}.task"
                if new_filepath.exists() and new_filepath != filepath:
                    messagebox.showerror("Error", "A task with this name already exists")
                    return
                filepath.rename(new_filepath)
                filepath = new_filepath
            
            task_data = {"title": new_title, "content": new_content}
            with open(filepath, "w") as f:
                json.dump(task_data, f)
            
            self.refresh_matrix_task_list()
    
    def delete_matrix_task(self, category):
        listbox = self.matrix_task_lists[category]
        selection = listbox.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a task to delete")
            return
        
        task_title = listbox.get(selection[0])
        filepath = self.get_category_path(category) / f"{self.sanitize_filename(task_title)}.task"
        
        if filepath.exists():
            if messagebox.askyesno("Confirm Delete", f"Delete task '{task_title}'?"):
                filepath.unlink()
                self.refresh_matrix_task_list()
    
    def move_matrix_to_do_first(self, category):
        listbox = self.matrix_task_lists[category]
        selection = listbox.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a task to move")
            return
        
        task_title = listbox.get(selection[0])
        source_path = self.get_category_path(category) / f"{self.sanitize_filename(task_title)}.task"
        dest_path = self.get_category_path("do_first") / f"{self.sanitize_filename(task_title)}.task"
        
        if dest_path.exists():
            messagebox.showerror("Error", "A task with this name already exists in Do First")
            return
        
        if source_path.exists():
            source_path.rename(dest_path)
            self.refresh_matrix_task_list()
            self._set_status(f"Task moved to Do First quadrant")
    
    def move_matrix_to_tasks(self, category):
        listbox = self.matrix_task_lists[category]
        selection = listbox.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a task to move")
            return
        
        task_title = listbox.get(selection[0])
        filepath = self.get_category_path(category) / f"{self.sanitize_filename(task_title)}.task"
        
        if not filepath.exists():
            messagebox.showerror("Error", "Task file not found")
            return
        
        try:
            with open(filepath, "r") as f:
                task_data = json.load(f)
        except:
            with open(filepath, "r") as f:
                content = f.read()
            task_data = {"title": task_title, "content": content}
        
        task_text = task_data["title"]
        task_desc = task_data["content"]
        new_task = Task(
            text=task_text,
            done=False,
            created_at=self._timestamp(),
            description=task_desc
        )
        self.tasks.insert(0, new_task)
        
        filepath.unlink()
        self.refresh_matrix_task_list()
        self._refresh_all()
        self._set_status(f"Task '{task_text}' moved to main task list.")
        # Switch to main tab to show the moved task
        self.notebook.select(0)

    def copy_matrix_to_tasks(self, category):
        """Copy all tasks from a matrix quadrant to main tasks"""
        listbox = self.matrix_task_lists[category]
        count = listbox.size()
        if count == 0:
            self._set_status(f"No tasks in {category} quadrant to copy")
            return
            
        copied_count = 0
        cat_path = self.get_category_path(category)
        if cat_path.exists():
            for filepath in sorted(cat_path.glob("*.task")):
                try:
                    with open(filepath, "r") as f:
                        task_data = json.load(f)
                        task_text = task_data["title"]
                        task_desc = task_data["content"]
                        new_task = Task(
                            text=task_text,
                            done=False,
                            created_at=self._timestamp(),
                            description=task_desc
                        )
                        self.tasks.insert(0, new_task)
                        copied_count += 1
                except Exception as e:
                    print(f"Error copying task {filepath}: {e}")
        
        self._refresh_all()
        self._set_status(f"Copied {copied_count} tasks from {category} to main tasks")

    def add_task_from_capture(self):
        text = self.capture_entry.get().strip()
        if not text:
            return
        self.tasks.insert(0, Task(text=text, done=False, created_at=self._timestamp()))
        self.capture_entry.delete(0, tk.END)
        self._refresh_all()
        self._set_status("Captured as task.")
        if self.auto_save_enabled:
            self.save_state()

    def add_note_from_capture(self):
        text = self.capture_entry.get().strip()
        if not text:
            return
        self.notes.append(Note(text=text, created_at=self._timestamp()))
        self.capture_entry.delete(0, tk.END)
        self._refresh_notes()
        self._set_status("Captured in scratchpad.")
        if self.auto_save_enabled:
            self.save_state()

    def add_task_direct(self):
        text = self.task_entry.get().strip()
        if not text:
            return
        self.tasks.insert(0, Task(text=text, done=False, created_at=self._timestamp()))
        self.task_entry.delete(0, tk.END)
        self._refresh_all()
        self._set_status("Task added.")
        if self.auto_save_enabled:
            self.save_state()

    def mark_task_done(self):
        sel = self.task_list.curselection()
        if not sel:
            return
            
        display_tasks = self._get_display_tasks()
        
        # Handle multiple selections
        if len(sel) > 1:
            # Process in reverse order to maintain indices
            for idx in reversed(sel):
                if idx < len(display_tasks):
                    task = display_tasks[idx]
                    actual_idx = self.tasks.index(task)
                    self.tasks[actual_idx].done = not self.tasks[actual_idx].done
                    if self.tasks[actual_idx].done:
                        self.tasks[actual_idx].completed_at = self._timestamp()
                    else:
                        self.tasks[actual_idx].completed_at = None
        else:
            # Single selection
            idx = sel[0]
            if idx < len(display_tasks):
                task = display_tasks[idx]
                actual_idx = self.tasks.index(task)
                self.tasks[actual_idx].done = not self.tasks[actual_idx].done
                if self.tasks[actual_idx].done:
                    self.tasks[actual_idx].completed_at = self._timestamp()
                else:
                    self.tasks[actual_idx].completed_at = None
        
        self._refresh_all()
        self.task_list.selection_set(sel)
        self._set_status(f"Toggled {len(sel)} task(s) completion.")
        if self.auto_save_enabled:
            self.save_state()

    def delete_selected_task(self):
        sel = self.task_list.curselection()
        if not sel:
            return
            
        display_tasks = self._get_display_tasks()
        
        # Process in reverse order to maintain indices
        deleted_count = 0
        for idx in reversed(sel):
            if idx < len(display_tasks):
                task = display_tasks[idx]
                actual_idx = self.tasks.index(task)
                del self.tasks[actual_idx]
                deleted_count += 1
        
        self._refresh_all()
        self._set_status(f"Deleted {deleted_count} task(s).")
        if self.auto_save_enabled:
            self.save_state()

    def promote_selected_task(self):
        sel = self.task_list.curselection()
        if not sel or len(sel) > 1:  # Only allow promoting one task at a time
            return
            
        idx = sel[0]
        display_tasks = self._get_display_tasks()
        
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
            if self.auto_save_enabled:
                self.save_state()

    def toggle_high_priority(self):
        sel = self.task_list.curselection()
        if not sel:
            return
            
        display_tasks = self._get_display_tasks()
        
        # Handle multiple selections
        toggled_count = 0
        for idx in sel:
            if idx < len(display_tasks):
                task = display_tasks[idx]
                actual_idx = self.tasks.index(task)
                self.tasks[actual_idx].priority = 1 - self.tasks[actual_idx].priority
                toggled_count += 1
        
        self._refresh_all()
        self.task_list.selection_set(sel)
        self._set_status(f"Toggled high priority for {toggled_count} task(s).")
        if self.auto_save_enabled:
            self.save_state()

    def add_tag_to_task(self):
        sel = self.task_list.curselection()
        if not sel:
            return
            
        display_tasks = self._get_display_tasks()
        
        tag = simpledialog.askstring("Add Tag", "Enter tag name:")
        if not tag:
            return
            
        tag = tag.strip().lower()
        if not tag:
            return
            
        # Handle multiple selections
        tagged_count = 0
        for idx in sel:
            if idx < len(display_tasks):
                task = display_tasks[idx]
                actual_idx = self.tasks.index(task)
                if tag not in self.tasks[actual_idx].tags:
                    self.tasks[actual_idx].tags.append(tag)
                    tagged_count += 1
        
        self._refresh_all()
        self.task_list.selection_set(sel)
        self._set_status(f"Added tag '{tag}' to {tagged_count} task(s).")
        if self.auto_save_enabled:
            self.save_state()

    def edit_task_details(self):
        sel = self.task_list.curselection()
        if not sel or len(sel) > 1:  # Only allow editing one task at a time
            return
            
        idx = sel[0]
        display_tasks = self._get_display_tasks()
        
        if idx < len(display_tasks):
            task = display_tasks[idx]
            actual_idx = self.tasks.index(task)
            
            dialog = tk.Toplevel(self)
            dialog.title("Edit Task Details")
            dialog.geometry("400x300")
            dialog.transient(self)
            dialog.grab_set()
            
            ttk.Label(dialog, text="Task:").pack(anchor="w", padx=10, pady=(10, 0))
            task_text = tk.Text(dialog, height=3, wrap="word")
            task_text.pack(fill="x", padx=10, pady=(0, 10))
            task_text.insert("1.0", self.tasks[actual_idx].text)
            
            ttk.Label(dialog, text="Description:").pack(anchor="w", padx=10, pady=(0, 0))
            desc_text = tk.Text(dialog, height=8, wrap="word")
            desc_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            desc_text.insert("1.0", self.tasks[actual_idx].description)
            
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
                if self.auto_save_enabled:
                    self.save_state()
            
            ttk.Button(button_frame, text="Save", command=save_changes).pack(side="right", padx=5)
            ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side="right")
            
            dialog.update_idletasks()
            x = self.winfo_x() + self.winfo_width() // 2 - dialog.winfo_width() // 2
            y = self.winfo_y() + self.winfo_height() // 2 - dialog.winfo_height() // 2
            dialog.geometry(f"+{x}+{y}")

    def move_to_matrix(self):
        sel = self.task_list.curselection()
        if not sel or len(sel) > 1:  # Only allow moving one task at a time with this method
            return
            
        idx = sel[0]
        display_tasks = self._get_display_tasks()
        
        if idx < len(display_tasks):
            task = display_tasks[idx]
            actual_idx = self.tasks.index(task)
            
            dialog = MatrixSelectionDialog(self)
            self.wait_window(dialog.window)
            
            if dialog.result:
                quadrant = dialog.result
                title = self.tasks[actual_idx].text
                content = self.tasks[actual_idx].description or ""
                
                filename = f"{self.sanitize_filename(title)}.task"
                filepath = self.get_category_path(quadrant) / filename
                
                counter = 1
                base_name = title
                while filepath.exists():
                    title = f"{base_name}_{counter}"
                    filename = f"{self.sanitize_filename(title)}.task"
                    filepath = self.get_category_path(quadrant) / filename
                    counter += 1
                
                task_data = {"title": title, "content": content}
                with open(filepath, "w") as f:
                    json.dump(task_data, f)
                
                del self.tasks[actual_idx]
                self._refresh_all()
                self.refresh_matrix_task_list()
                self._set_status(f"Task moved to {quadrant.replace('_', ' ').title()} quadrant.")
                # Switch to matrix tab to show the moved task
                self.notebook.select(1)

    def move_selected_tasks_to_matrix(self):
        """Move multiple selected tasks to matrix"""
        sel = self.task_list.curselection()
        if not sel:
            messagebox.showwarning("No Selection", "Please select tasks to move")
            return
        
        # Get actual task indices (accounting for sorting/filtering)
        display_tasks = self._get_display_tasks()
        selected_tasks = []
        
        for idx in sel:
            if idx < len(display_tasks):
                task = display_tasks[idx]
                actual_idx = self.tasks.index(task)
                selected_tasks.append((actual_idx, task))
        
        # Show matrix selection dialog
        dialog = MatrixSelectionDialog(self, multiple=True, title="Select Matrix Quadrant for Batch Move")
        self.wait_window(dialog.window)
        
        if dialog.result:
            quadrant = dialog.result
            moved_count = 0
            
            # Move tasks in reverse order to maintain indices
            for actual_idx, task in sorted(selected_tasks, key=lambda x: x[0], reverse=True):
                title = self.tasks[actual_idx].text
                content = self.tasks[actual_idx].description or ""
                
                filename = f"{self.sanitize_filename(title)}.task"
                filepath = self.get_category_path(quadrant) / filename
                
                # Handle duplicates
                counter = 1
                base_name = title
                while filepath.exists():
                    title = f"{base_name}_{counter}"
                    filename = f"{self.sanitize_filename(title)}.task"
                    filepath = self.get_category_path(quadrant) / filename
                    counter += 1
                
                # Save to matrix
                task_data = {"title": title, "content": content}
                with open(filepath, "w") as f:
                    json.dump(task_data, f)
                
                # Remove from main list
                del self.tasks[actual_idx]
                moved_count += 1
            
            self._refresh_all()
            self.refresh_matrix_task_list()
            self._set_status(f"Moved {moved_count} tasks to {quadrant.replace('_', ' ').title()}")
            # Switch to matrix tab to show the moved tasks
            self.notebook.select(1)

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
        if self.auto_save_enabled:
            self.save_state()

    def clear_notes(self):
        if not messagebox.askyesno("Clear scratchpad", "Clear all notes from the scratchpad?"):
            return
        self.notes.clear()
        self.note_text.delete("1.0", tk.END)
        self._set_status("Scratchpad cleared.")
        if self.auto_save_enabled:
            self.save_state()

    def brain_dump_into_tasks(self):
        raw = self.note_text.get("1.0", tk.END).strip()
        if not raw:
            return
        lines = [line.strip("-• \t") for line in raw.splitlines() if line.strip()]
        added_count = 0
        for line in lines:
            if line:
                self.tasks.insert(0, Task(text=line, done=False, created_at=self._timestamp()))
                added_count += 1
        self._refresh_all()
        self._set_status(f"Moved {added_count} line(s) into tasks.")
        if self.auto_save_enabled:
            self.save_state()

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
            self.last_auto_save = time.time()
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

    def _start_auto_save(self):
        self._check_auto_save()
    
    def _check_auto_save(self):
        if self.auto_save_enabled and time.time() - self.last_auto_save > self.auto_save_interval:
            try:
                with open(self.current_file, "r", encoding="utf-8") as f:
                    current_data = json.load(f)
                if current_data != self.to_dict():
                    self.save_state()
            except FileNotFoundError:
                self.save_state()
            except Exception:
                pass
        
        self.after(5000, self._check_auto_save)

    def on_close(self):
        try:
            self.save_state()
        finally:
            self.destroy()

if __name__ == "__main__":
    app = CognitiveOffloadApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()