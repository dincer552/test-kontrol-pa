"""Windows UI regression: every top-level page remains available."""
import sys

import pytest

if sys.platform != "win32":
    pytest.skip("Notebook visibility is verified on the Windows build runner.", allow_module_level=True)

from app import TestControlApp


def test_all_top_level_tabs_are_visible_and_selectable_without_unlock_steps():
    app = TestControlApp()
    try:
        app.update_idletasks()
        expected_page_count = 8
        tab_ids = app.tabs.tabs()

        assert len(tab_ids) == expected_page_count
        assert len(app._tab_ids) == expected_page_count

        for tab_id in tab_ids:
            assert app.tabs.tab(tab_id, "state") == "normal"

        # Older callers may still request a page to be hidden. The compatibility
        # method must never reintroduce a page-visibility gate.
        for page_name in app._tab_sequence:
            app._set_tab_visible(page_name, False)
            tab_id = app._tab_ids[page_name]
            assert app.tabs.tab(tab_id, "state") == "normal"

        # Verify each page can actually be selected without connecting,
        # importing a PDF, or saving the page before it.
        for tab_id in tab_ids:
            app.tabs.select(tab_id)
            app.update_idletasks()
            assert app.tabs.select() == tab_id
    finally:
        app.destroy()
