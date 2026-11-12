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



def test_update_button_is_compact_above_green_version_label_at_400px():
    app = TestControlApp()
    try:
        app.geometry("400x820")
        app.update_idletasks()

        assert app._update_button.winfo_manager() == "pack"
        assert app._update_build_label.winfo_manager() == "pack"
        button_info = app._update_button.pack_info()
        label_info = app._update_build_label.pack_info()

        assert button_info.get("side") == "top"
        assert label_info.get("side") == "top"
        assert app._update_button.master is app._update_build_label.master
        assert app.tk.call("ttk::style", "lookup", "UpdateBuild.TLabel", "-foreground") == "#16a34a"
        assert app._update_button.winfo_width() <= app.winfo_width()
        # Until a newer release is detected, the version label stays empty
        # and disabled; it is populated and enabled only for an available update.
        assert app._update_build_label.cget("text") == ""
        assert "disabled" in app._update_build_label.state()
    finally:
        app.destroy()
