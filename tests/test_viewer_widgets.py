"""Real Tk widgets, isolated by the existing Windows GUI test runner."""

import pytest

from transmitracker.viewer.app import Viewer
from transmitracker.viewer.demo import make_demo

pytestmark = pytest.mark.gui


def test_manual_selection_timeline_and_canvas_have_only_observed_markers():
    app = Viewer(make_demo())
    failures = []
    app.report_callback_exception = lambda *args: failures.append(args)
    try:
        app.update()
        assert app.winfo_ismapped()
        assert len(app.canvas.find_withtag("geometry")) == 2
        assert len(app.canvas.find_withtag("observed")) == 1
        app.vehicles.selection_set("1")
        app.update()
        assert app.candidate_index == 1
        app.set_cursor(7)
        app.update()
        assert app.cursor == 7
        assert len(app.canvas.find_withtag("observed")) == 8
        assert "Bajo movimiento" in app.details.get("1.0", "end")
        app.select_candidate(0)
        app.set_cursor(6)
        app.update()
        assert len(app.canvas.find_withtag("visual_link")) == 5  # 2 + 3, never across route change
        app.segments.selection_set("0")
        app.update()
        assert app.cursor == 0
        app.select_candidate(2)
        app.set_cursor(7)
        app.update()
        assert not app.canvas.find_withtag("visual_link")
        assert "Ambiguo" in app.details.get("1.0", "end")
        assert "DEMO-S1" in app.details.get("1.0", "end")
        assert "DEMO-S2" in app.details.get("1.0", "end")
        app.fit(False)
        app.magnify(1.25)
        app.update()
        assert app.zoom == 1.25
        assert not failures
    finally:
        app.destroy()
