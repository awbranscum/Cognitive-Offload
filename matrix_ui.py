# File: matrix_ui.py
import tkinter as tk
from tkinter import ttk, messagebox

def build_matrix_ui(app):
    root = app.matrix_frame
    
    header = ttk.Frame(root)
    header.pack(fill="x", padx=10, pady=5)
    tk.Label(header, text="Eisenhower Matrix - Task Prioritization", font=("Helvetica", 18, "bold"), bg="#f5f6f8").pack(anchor="w")
    tk.Label(
        header,
        text="Organize tasks by urgency and importance. Only one quadrant visible at a time.",
        font=("Helvetica", 10), bg="#f5f6f8", fg="#555"
    ).pack(anchor="w", pady=(2, 10))
    
    db_frame = ttk.Frame(header)
    db_frame.pack(fill="x", pady=(0, 10))
    tk.Label(db_frame, text="Matrix Database:", bg="#f5f6f8").pack(side="left")
    app.matrix_path_label = tk.Label(db_frame, text=str(app.matrix_db_path), fg="#0066cc", bg="#f5f6f8")
    app.matrix_path_label.pack(side="left", padx=(5, 10))
    ttk.Button(db_frame, text="Change Folder", command=app.change_matrix_db_folder).pack(side="left")
    ttk.Button(db_frame, text="Refresh", command=app.refresh_matrix_task_list).pack(side="left", padx=(5, 0))
    ttk.Button(db_frame, text="← Back to Tasks", command=lambda: app.notebook.select(0)).pack(side="right")
    
    matrix_notebook = ttk.Notebook(root)
    matrix_notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
    
    app.matrix_quadrants = {}
    app.matrix_task_lists = {}
    
    categories = ["do_first", "schedule", "delegate", "eliminate"]
    titles = ["Do First\n(Urgent/Important)", "Schedule\n(Not Urgent/Important)",
             "Delegate\n(Urgent/Not Important)", "Eliminate\n(Not Urgent/Not Important)"]
    colors = ["#FFCCCC", "#CCCCFF", "#FFFFCC", "#EEEEEE"]
    
    for cat, title, color in zip(categories, titles, colors):
        frame = ttk.Frame(matrix_notebook)
        matrix_notebook.add(frame, text=title.split('\n')[0])
        
        quad_header = ttk.Frame(frame)
        quad_header.pack(fill="x", padx=10, pady=5)
        tk.Label(quad_header, text=title.replace('\n', ' - '), font=("Helvetica", 14, "bold"), bg="#e8f4f8").pack(side="left")
        
        content_frame = ttk.Frame(frame)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        content_frame.columnconfigure(1, weight=1)
        content_frame.rowconfigure(0, weight=1)
        
        listbox = tk.Listbox(content_frame, bg=color, height=20, selectmode=tk.EXTENDED)
        listbox.grid(row=0, column=1, sticky="nsew", padx=(0, 5))
        listbox.bind('<Double-1>', lambda e, c=cat: app.edit_matrix_task(c))
        listbox.bind('<Delete>', lambda e, c=cat: app.delete_matrix_task(c))
        
        task_scroll = ttk.Scrollbar(content_frame, orient="vertical", command=listbox.yview)
        task_scroll.grid(row=0, column=2, sticky="ns")
        listbox.configure(yscrollcommand=task_scroll.set)
        
        btn_frame = ttk.Frame(content_frame)
        btn_frame.grid(row=0, column=0, sticky="nw", padx=(0, 10))
        
        ttk.Button(btn_frame, text="Add Task",
                  command=lambda c=cat: app.add_matrix_task(c)).pack(fill="x", pady=2)
        
        ttk.Button(btn_frame, text="Edit Task",
                  command=lambda c=cat: app.edit_matrix_task(c)).pack(fill="x", pady=2)
        
        ttk.Button(btn_frame, text="Delete Task",
                  command=lambda c=cat: app.delete_matrix_task(c)).pack(fill="x", pady=2)
        
        if cat != "do_first":
            ttk.Button(btn_frame, text="Move to Do First",
                      command=lambda c=cat: app.move_matrix_to_do_first(c)).pack(fill="x", pady=2)
        
        ttk.Button(btn_frame, text="To Main Tasks",
                  command=lambda c=cat: app.move_matrix_to_tasks(c)).pack(fill="x", pady=2)
        
        # Quick action buttons
        ttk.Button(btn_frame, text="📋 Copy to Tasks",
                  command=lambda c=cat: app.copy_matrix_to_tasks(c)).pack(fill="x", pady=2)
        
        app.matrix_task_lists[cat] = listbox
        app.matrix_quadrants[cat] = frame
    
    app.refresh_matrix_task_list()