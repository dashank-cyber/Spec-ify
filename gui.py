"""
gui.py — Tkinter interface for Spec-ify.

Three screens, all in one window (frames swapped in/out):
  1. Selection screen — device type, budget range, usage-tag categories
     (up to 3), and criteria weight sliders.                         (FR2, FR3)
  2. Results screen — ranked list of scored devices with price + a
     pros/cons snippet, and checkboxes to pick 2-3 for comparison.    (FR5, FR6, FR7)
  3. Comparison screen — selected devices shown side-by-side.         (FR8)
"""

import tkinter as tk
from tkinter import ttk, messagebox

import db
import scoring

MAX_CATEGORY_TAGS = 3
MAX_COMPARE = 3


class SpecifyApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Spec-ify — Device Recommender")
        self.geometry("900x650")
        self.minsize(760, 560)

        self.device_type = tk.StringVar(value="phone")
        self.category_vars = {}       # category -> BooleanVar
        self.weight_vars = {}         # criterion_key -> IntVar (0-5)
        self.results = []             # last scored results
        self.compare_vars = {}        # device_id -> BooleanVar (results screen)

        self._build_selection_screen()

    # ------------------------------------------------------------------
    # Screen 1: Selection
    # ------------------------------------------------------------------
    def _build_selection_screen(self):
        self.selection_frame = ttk.Frame(self, padding=16)
        self.selection_frame.pack(fill="both", expand=True)
        f = self.selection_frame

        ttk.Label(f, text="Spec-ify", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(f, text="Find the right device for your budget and needs.",
                  font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 16))

        # --- device type ---
        type_frame = ttk.LabelFrame(f, text="Device type", padding=10)
        type_frame.pack(fill="x", pady=6)
        ttk.Radiobutton(type_frame, text="Phone", variable=self.device_type,
                         value="phone", command=self._on_type_change).pack(side="left", padx=8)
        ttk.Radiobutton(type_frame, text="Laptop", variable=self.device_type,
                         value="laptop", command=self._on_type_change).pack(side="left", padx=8)

        # --- budget ---
        budget_frame = ttk.LabelFrame(f, text="Budget range (Rs.)", padding=10)
        budget_frame.pack(fill="x", pady=6)
        ttk.Label(budget_frame, text="Min:").grid(row=0, column=0, padx=4)
        self.budget_min_entry = ttk.Entry(budget_frame, width=10)
        self.budget_min_entry.insert(0, "10000")
        self.budget_min_entry.grid(row=0, column=1, padx=4)
        ttk.Label(budget_frame, text="Max:").grid(row=0, column=2, padx=4)
        self.budget_max_entry = ttk.Entry(budget_frame, width=10)
        self.budget_max_entry.insert(0, "50000")
        self.budget_max_entry.grid(row=0, column=3, padx=4)

        # --- categories ---
        self.category_frame = ttk.LabelFrame(
            f, text=f"Usage tags (pick up to {MAX_CATEGORY_TAGS})", padding=10)
        self.category_frame.pack(fill="x", pady=6)
        self._render_category_checkboxes()

        # --- weights ---
        self.weight_frame = ttk.LabelFrame(f, text="How much do you care about each?", padding=10)
        self.weight_frame.pack(fill="both", pady=6, expand=False)
        self._render_weight_sliders()

        # --- submit ---
        ttk.Button(f, text="Find recommendations",
                   command=self._on_find_recommendations).pack(pady=16)

    def _render_category_checkboxes(self):
        for widget in self.category_frame.winfo_children():
            widget.destroy()
        self.category_vars = {}
        cats = db.get_categories_for_type(self.device_type.get())
        for i, cat in enumerate(cats):
            var = tk.BooleanVar(value=False)
            self.category_vars[cat] = var
            cb = ttk.Checkbutton(self.category_frame, text=cat, variable=var,
                                  command=self._enforce_category_limit)
            cb.grid(row=i // 4, column=i % 4, sticky="w", padx=6, pady=2)

    def _enforce_category_limit(self):
        selected = [c for c, v in self.category_vars.items() if v.get()]
        if len(selected) > MAX_CATEGORY_TAGS:
            messagebox.showinfo("Limit reached", f"You can pick up to {MAX_CATEGORY_TAGS} tags.")
            # undo the most recent selection (last one alphabetically checked is ambiguous,
            # so just uncheck one arbitrarily from the overflow — simplest fix for a mini project)
            for c in selected:
                if len(selected) <= MAX_CATEGORY_TAGS:
                    break
                self.category_vars[c].set(False)
                selected.remove(c)

    def _render_weight_sliders(self):
        for widget in self.weight_frame.winfo_children():
            widget.destroy()

        self.weight_vars = {}
        criteria = scoring.criteria_for(self.device_type.get())

        for i, (key, (label, _)) in enumerate(criteria.items()):
            var = tk.IntVar(value=3)
            self.weight_vars[key] = var

            ttk.Label(self.weight_frame,text=label,width=18).grid(row=i, column=0, sticky="w", pady=4)
            value_label = ttk.Label(self.weight_frame,text="0",width=3)
            value_label.grid(row=i,column=2,padx=(4, 0),sticky="w")

            def update_value(value, variable=var, display=value_label):
                rounded = round(float(value))
                variable.set(rounded)
                display.config(text=str(rounded))

            ttk.Scale(self.weight_frame,from_=0,to=5,orient="horizontal",length=220,command=update_value).grid(row=i, column=1, padx=8)
    
    def _on_type_change(self):
        self._render_category_checkboxes()
        self._render_weight_sliders()

    def _on_find_recommendations(self):
        try:
            budget_min = float(self.budget_min_entry.get())
            budget_max = float(self.budget_max_entry.get())
        except ValueError:
            messagebox.showerror("Invalid budget", "Please enter numeric budget values.")
            return
        if budget_min > budget_max:
            messagebox.showerror("Invalid budget", "Min budget can't be greater than max budget.")
            return

        device_type = self.device_type.get()
        selected_categories = [c for c, v in self.category_vars.items() if v.get()]
        weights = {k: v.get() for k, v in self.weight_vars.items()}

        devices = db.fetch_devices(device_type, budget_min, budget_max, selected_categories)
        if not devices:
            messagebox.showinfo("No matches",
                                 "No devices matched your budget/tags. Try widening the range.")
            return

        scored = scoring.score_devices(devices, device_type, weights)
        self.results = scored
        self._build_results_screen(device_type)

    # ------------------------------------------------------------------
    # Screen 2: Results
    # ------------------------------------------------------------------
    def _build_results_screen(self, device_type):
        self.selection_frame.pack_forget()
        self.results_frame = ttk.Frame(self, padding=16)
        self.results_frame.pack(fill="both", expand=True)
        f = self.results_frame

        header = ttk.Frame(f)
        header.pack(fill="x")
        ttk.Label(header, text=f"Top matches ({len(self.results)} found)",
                  font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Button(header, text="< Back to search", command=self._back_to_selection).pack(side="right")

        columns = ("select", "rank", "model", "score", "price", "categories")
        tree_frame = ttk.Frame(f)
        tree_frame.pack(fill="both", expand=True, pady=10)

        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=14)
        headings = {"select": "Compare", "rank": "#", "model": "Model", "score": "Score",
                    "price": "Price Range (Rs.)", "categories": "Tags"}
        widths = {"select": 70, "rank": 30, "model": 220, "score": 60,
                  "price": 150, "categories": 220}
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor="w")

        self.compare_vars = {}
        for i, device in enumerate(self.results, start=1):
            price = f"{int(device['price_min']):,} - {int(device['price_max']):,}"
            cats = ", ".join(device["categories"])
            self.tree.insert("", "end", iid=str(device["id"]),
                              values=("[ ]", i, device["model"], f"{device['score']:.2f}", price, cats))

        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.pack(fill="both", expand=True, side="left")

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        # pros/cons detail panel
        detail_frame = ttk.LabelFrame(f, text="Details (click a row)", padding=8)
        detail_frame.pack(fill="x", pady=(6, 0))
        self.detail_label = ttk.Label(detail_frame, text="Select a device to see pros/cons.",
                                       wraplength=820, justify="left")
        self.detail_label.pack(anchor="w")
        self.tree.bind("<<TreeviewSelect>>", self._on_row_select)

        footer = ttk.Frame(f)
        footer.pack(fill="x", pady=10)
        ttk.Label(footer, text=f"Select 2-{MAX_COMPARE} devices above, then compare.").pack(side="left")
        ttk.Button(footer, text="Compare selected",
                   command=lambda: self._build_comparison_screen(device_type)).pack(side="right")

    def _on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        row_id = self.tree.identify_row(event.y)
        if col != "#1" or not row_id:  # "#1" = select column
            return
        current = self.compare_vars.get(row_id, False)
        if not current and sum(self.compare_vars.values()) >= MAX_COMPARE:
            messagebox.showinfo("Limit reached", f"You can compare up to {MAX_COMPARE} devices.")
            return
        self.compare_vars[row_id] = not current
        vals = list(self.tree.item(row_id, "values"))
        vals[0] = "[x]" if self.compare_vars[row_id] else "[ ]"
        self.tree.item(row_id, values=vals)

    def _on_row_select(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        device_id = int(selected[0])
        device = next((d for d in self.results if d["id"] == device_id), None)
        if device:
            text = f"Pros: {device.get('pros') or 'N/A'}\nCons: {device.get('cons') or 'N/A'}"
            self.detail_label.config(text=text)

    def _back_to_selection(self):
        self.results_frame.pack_forget()
        self.selection_frame.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # Screen 3: Comparison
    # ------------------------------------------------------------------
    def _build_comparison_screen(self, device_type):
        chosen_ids = [rid for rid, checked in self.compare_vars.items() if checked]
        if len(chosen_ids) < 2:
            messagebox.showinfo("Pick more devices", "Select at least 2 devices to compare.")
            return

        self.results_frame.pack_forget()
        self.compare_frame = ttk.Frame(self, padding=16)
        self.compare_frame.pack(fill="both", expand=True)
        f = self.compare_frame

        header = ttk.Frame(f)
        header.pack(fill="x")
        ttk.Label(header, text="Side-by-side comparison",
                  font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Button(header, text="< Back to results", command=self._back_to_results).pack(side="right")

        devices = [db.fetch_device_by_id(device_type, int(did)) for did in chosen_ids]
        criteria = scoring.criteria_for(device_type)

        table = ttk.Frame(f)
        table.pack(fill="both", expand=True, pady=12)

        # header row: attribute label + one column per device
        ttk.Label(table, text="Attribute", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, sticky="w", padx=6, pady=4)
        for c, device in enumerate(devices, start=1):
            ttk.Label(table, text=device["model"], font=("Segoe UI", 10, "bold"),
                      wraplength=180).grid(row=0, column=c, sticky="w", padx=6, pady=4)

        rows = [("Price Range (Rs.)",
                 lambda d: f"{int(d['price_min']):,} - {int(d['price_max']):,}")]
        # show raw spec text (not the numeric score) for readability
        spec_cols = ["ram", "storage", "processor"] + \
                    (["gpu"] if device_type == "laptop" else ["battery"]) + ["display"]
        for col in spec_cols:
            rows.append((col.capitalize(), (lambda c: lambda d: d.get(c) or "N/A")(col)))
        rows.append(("Tags", lambda d: ", ".join(d["categories"]) or "N/A"))
        rows.append(("Pros", lambda d: d.get("pros") or "N/A"))
        rows.append(("Cons", lambda d: d.get("cons") or "N/A"))

        for r, (label, getter) in enumerate(rows, start=1):
            ttk.Label(table, text=label, font=("Segoe UI", 9, "bold")).grid(
                row=r, column=0, sticky="nw", padx=6, pady=4)
            for c, device in enumerate(devices, start=1):
                ttk.Label(table, text=str(getter(device)), wraplength=180,
                          justify="left").grid(row=r, column=c, sticky="nw", padx=6, pady=4)

    def _back_to_results(self):
        self.compare_frame.pack_forget()
        self.results_frame.pack(fill="both", expand=True)
