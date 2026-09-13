"""
db.py — Database access layer for Spec-ify.

Handles all SQLite interaction for the two device tables (phones, laptops)
and their category junction tables (phone_categories, laptop_categories).
Keeping every query in one place means the GUI and scoring code never
have to write raw SQL themselves — FR1 (SQL storage) and the
"maintainability" non-functional requirement from the spec.
"""

import sqlite3
import os

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATHS = {
    "phone": os.path.join(DATA_DIR, "phones.db"),
    "laptop": os.path.join(DATA_DIR, "laptops.db"),
}

TABLE_NAMES = {
    "phone": ("phones", "phone_categories", "phone_id"),
    "laptop": ("laptops", "laptop_categories", "laptop_id"),
}

ALL_CATEGORIES = [
    "Budget-friendly", "Flagship-level", "Casual",
    "Gaming", "Battery", "Performance", "Coding",
]


def _connect(device_type):
    """Open a connection to the right SQLite file, with rows as dicts."""
    path = DB_PATHS[device_type]
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"\n\nCouldn't find the database file at:\n  {path}\n\n"
            f"Make sure phones.db and laptops.db sit directly next to "
            f"db.py, gui.py, and main.py.\n"
            f"Expected folder layout:\n"
            f"  Spec-ify/\n"
            f"    main.py\n    gui.py\n    scoring.py\n    db.py\n"
            f"    phones.db\n    laptops.db\n"
        )
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def get_categories_for_type(device_type):
    """Categories that actually apply to this device type (laptops get 'Coding' too)."""
    if device_type == "laptop":
        return ALL_CATEGORIES
    return [c for c in ALL_CATEGORIES if c != "Coding"]


def fetch_devices(device_type, budget_min=None, budget_max=None, selected_categories=None):
    """
    Fetch devices for a given type, optionally filtered by budget range
    (hard filter — a device's price_min/price_max must overlap the user's
    budget) and by usage-tag categories (a device matches if it has AT
    LEAST ONE of the selected tags).

    Returns a list of dicts, each with all device columns plus a
    'categories' list.
    """
    table, junction, fk = TABLE_NAMES[device_type]
    conn = _connect(device_type)
    cur = conn.cursor()

    query = f"SELECT * FROM {table}"
    conditions = []
    params = []

    if budget_min is not None and budget_max is not None:
        # Overlap test: device range intersects [budget_min, budget_max]
        conditions.append("price_min <= ? AND price_max >= ?")
        params.extend([budget_max, budget_min])

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]

    # attach categories to each device
    for row in rows:
        cur.execute(f"SELECT category FROM {junction} WHERE {fk} = ?", (row["id"],))
        row["categories"] = [c[0] for c in cur.fetchall()]

    conn.close()

    if selected_categories:
        selected = set(selected_categories)
        rows = [r for r in rows if selected.intersection(r["categories"])]

    return rows


def fetch_device_by_id(device_type, device_id):
    """Full detail for one device, including its categories — used by the comparison view."""
    table, junction, fk = TABLE_NAMES[device_type]
    conn = _connect(device_type)
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table} WHERE id = ?", (device_id,))
    row = cur.fetchone()
    if row is None:
        conn.close()
        return None
    device = dict(row)
    cur.execute(f"SELECT category FROM {junction} WHERE {fk} = ?", (device_id,))
    device["categories"] = [c[0] for c in cur.fetchall()]
    conn.close()
    return device


def count_devices(device_type):
    table, _, _ = TABLE_NAMES[device_type]
    conn = _connect(device_type)
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    n = cur.fetchone()[0]
    conn.close()
    return n
