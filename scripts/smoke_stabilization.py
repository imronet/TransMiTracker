"""Reproducible Windows/Tk visual smoke, using synthetic profiles only.

Run from project root, with PYTHONPATH=src and dev dependencies installed.
Output directories must be new, inside the project. No network is allowed.
"""

import argparse
import base64
import ctypes
import hashlib
import json
import socket
import struct
import subprocess
import sys
import time
from ctypes import wintypes
from dataclasses import replace
from datetime import time as wall_time
from pathlib import Path

import customtkinter as ctk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_catalog import write_zip  # noqa: E402
from test_stabilization import late_profile  # noqa: E402
from test_static_planning import planning_tables  # noqa: E402

from transmitracker.catalog.importer import import_catalog  # noqa: E402
from transmitracker.catalog.queries import Catalog  # noqa: E402
from transmitracker.gui.app import TransMiTrackerApp  # noqa: E402
from transmitracker.gui.controller import DesktopController  # noqa: E402
from transmitracker.gui.editor import ProfileEditor  # noqa: E402
from transmitracker.profiles.contracts import primitive  # noqa: E402
from transmitracker.profiles.models import ProfileKind  # noqa: E402


def blocked(*args, **kwargs):
    raise AssertionError("Network forbidden in the synthetic visual smoke")


def window_bitmap(app, path):
    """Render this process's client HWND, never copy the user's desktop."""
    user, gdi = ctypes.windll.user32, ctypes.windll.gdi32
    handle, integer = wintypes.HANDLE, ctypes.c_int
    for api, arguments, result in (
        (user.GetDC, [handle], handle),
        (user.ReleaseDC, [handle, handle], integer),
        (user.PrintWindow, [handle, handle, wintypes.UINT], wintypes.BOOL),
        (gdi.CreateCompatibleDC, [handle], handle),
        (gdi.CreateCompatibleBitmap, [handle, integer, integer], handle),
        (gdi.SelectObject, [handle, handle], handle),
        (gdi.DeleteObject, [handle], wintypes.BOOL),
        (gdi.DeleteDC, [handle], wintypes.BOOL),
        (
            gdi.GetDIBits,
            [
                handle,
                handle,
                wintypes.UINT,
                wintypes.UINT,
                ctypes.c_void_p,
                ctypes.c_void_p,
                wintypes.UINT,
            ],
            integer,
        ),
    ):
        api.argtypes, api.restype = arguments, result
    hwnd = app.winfo_id()
    width, height = app.winfo_width(), app.winfo_height()
    dc = user.GetDC(hwnd)
    memory = gdi.CreateCompatibleDC(dc)
    bitmap = gdi.CreateCompatibleBitmap(dc, width, height)
    previous = gdi.SelectObject(memory, bitmap)
    try:
        if not user.PrintWindow(hwnd, memory, 3):
            raise RuntimeError("Cannot render the synthetic Tk window")
        gdi.SelectObject(memory, previous)
        size = width * height * 4
        info = ctypes.create_string_buffer(
            struct.pack("<IiiHHIIiiII", 40, width, height, 1, 32, 0, size, 0, 0, 0, 0)
        )
        pixels = ctypes.create_string_buffer(size)
        if gdi.GetDIBits(memory, bitmap, 0, height, pixels, info, 0) != height:
            raise RuntimeError("Cannot read the synthetic window bitmap")
        path.write_bytes(
            struct.pack("<2sIHHI", b"BM", 54 + size, 0, 0, 54) + info.raw[:40] + pixels.raw
        )
    finally:
        gdi.SelectObject(memory, previous)
        gdi.DeleteObject(bitmap)
        gdi.DeleteDC(memory)
        user.ReleaseDC(hwnd, dc)


def pump(app, condition=lambda: False, seconds=0.4):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.update()
        if condition():
            return
        time.sleep(0.01)
    if seconds > 1:
        raise AssertionError("Local GUI operation timed out")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--screenshots", required=True)
    parser.add_argument(
        "--additional-views", action="store_true", help="Lower editor fields and a 900x650 result"
    )
    args = parser.parse_args()
    directory, screenshots = [
        (ROOT / value).resolve() for value in (args.directory, args.screenshots)
    ]
    if any(not p.is_relative_to(ROOT) or p.exists() for p in (directory, screenshots)):
        raise ValueError("Use new directories within the project")
    directory.mkdir(parents=True)
    screenshots.mkdir(parents=True)
    socket.socket.connect = blocked
    socket.create_connection = blocked
    catalog_path = directory / "catalog.sqlite3"
    import_catalog(write_zip(directory / "synthetic.zip", planning_tables()), catalog_path)
    controller = DesktopController(directory)
    preferences = controller.config.read()
    preferences["catalog_path"] = "catalog.sqlite3"
    controller.config.write(preferences)
    controller.bootstrap()
    with Catalog(catalog_path) as catalog:
        late = late_profile(catalog, 2)
    positive = replace(late, arrival_deadline=wall_time(8, 50))
    returning = replace(
        positive,
        kind=ProfileKind.TO_HOME,
        profile_id="SYNTHETIC_RETURN",
        usual_departure=wall_time(7, 55, 30, 500000),
    )
    assert controller.save_configuration(primitive(positive), 0).ok
    assert controller.save_configuration(primitive(returning), 0).ok
    app = TransMiTrackerApp(directory)
    errors, pictures = [], []
    app.report_callback_exception = lambda *error: errors.append(str(error))

    def capture(name, scroll=0):
        app.page._parent_canvas.yview_moveto(scroll)
        app.lift()
        pump(app)
        path = screenshots / (name + ".png")
        bitmap = directory / (name + ".bmp")
        window_bitmap(app, bitmap)
        script = f"""Add-Type -AssemblyName System.Drawing
$bitmap = [System.Drawing.Bitmap]::FromFile('{str(bitmap).replace(chr(39), chr(39) * 2)}')
$bitmap.Save('{str(path).replace(chr(39), chr(39) * 2)}', [System.Drawing.Imaging.ImageFormat]::Png)
$bitmap.Dispose()
"""
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-EncodedCommand",
                base64.b64encode(script.encode("utf-16le")).decode("ascii"),
            ],
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        pictures.append(
            {
                "file": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )

    try:
        pump(app, lambda: app.snapshot is not None, 10)
        app.geometry("1180x820")
        revision = 1
        for theme in ("light", "dark"):
            ctk.set_appearance_mode(theme)
            assert controller.save_configuration(primitive(positive), revision).ok
            revision += 1
            app.snapshot = controller.bootstrap()
            app.dashboard()
            pump(app)
            if not args.additional_views:
                capture(theme + "-dashboard")
            for kind, label in (
                (ProfileKind.TO_WORK, "work-editor"),
                (ProfileKind.TO_HOME, "return-editor"),
            ):
                app.open_profile(kind)
                pump(app, lambda: isinstance(app.page, ProfileEditor), 10)
                capture(
                    theme + "-" + label + ("-lower" if args.additional_views else ""),
                    1 if args.additional_views else 0,
                )
            cases = (
                ((positive, "positive"),)
                if args.additional_views
                else ((positive, "positive"), (late, "negative"))
            )
            for profile, label in cases:
                if label == "negative":
                    assert controller.save_configuration(primitive(late), revision).ok
                    revision += 1
                app.snapshot = controller.bootstrap()
                stored = next(
                    s
                    for s in app.snapshot["profiles"].data
                    if s.profile.profile_id == profile.profile_id
                )
                app.open_static_planning(stored)
                panel = app.planning_panel
                panel.day_var.set("2026-11-09")
                panel.request()
                pump(app, lambda p=panel: p.last_result is not None, 10)
                assert panel.last_result.ok == (label == "positive")
                if args.additional_views:
                    if label == "positive":
                        app.geometry("900x650")
                        capture(theme + "-positive-small")
                        app.geometry("1180x820")
                else:
                    capture(theme + "-" + label)
                    capture(theme + "-" + label + "-detail", 0.55)
        assert not errors, errors
    finally:
        app.close()
    output = {
        "synthetic_only": True,
        "network_requests": 0,
        "callback_errors": errors,
        "screenshots": pictures,
        "visual_review": "Pending human/model inspection of PNGs; execution alone is not visual approval",
    }
    (directory / "visual-smoke.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {"screenshots": len(pictures), "callback_errors": len(errors), "synthetic_only": True}
        )
    )


if __name__ == "__main__":
    main()
