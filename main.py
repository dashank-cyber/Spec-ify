"""
main.py — Entry point for Spec-ify.

Run with: python main.py
Requires: Python 3.8+ (stdlib only — tkinter + sqlite3, no external
packages, matching the "Portability" non-functional requirement).
"""

from gui import SpecifyApp

if __name__ == "__main__":
    app = SpecifyApp()
    app.mainloop()
