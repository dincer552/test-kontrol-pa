"""Compatibility bridge: the TEST KONTROL GÜNCELLE button uses the real updater.

The application historically imported Python's ``webbrowser`` module and called
``webbrowser.open(...)`` from the update button. Keeping this tiny bridge lets
that existing UI call flow into the VM-manifest updater without opening a web
page. No other browser functionality is used by TEST KONTROL.
"""
from __future__ import annotations

from updater import start_update


def open(url: str, new: int = 0, autoraise: bool = True) -> bool:
    """Start the Test Control self-update instead of opening a release page."""
    del url, new, autoraise
    try:
        # app.py owns the Tk root, so locate it through the active Tk default
        # root and pass it to the updater.
        import tkinter as tk
        parent = tk._default_root
        if parent is None:
            return False
        start_update(parent)
        return True
    except Exception:
        return False
