from pathlib import Path

import tkinter as tk

from companion.window import AnimatedAsset, DesktopWindow


def test_window_module_exports_gui_types():
    assert AnimatedAsset is not None
    assert DesktopWindow is not None


def test_animated_asset_loads_gif_frames_and_durations(monkeypatch, tmp_path):
    gif = tmp_path / "animated.gif"
    # Two Graphic Control Extensions with 10cs and 25cs delays.
    gif.write_bytes(b"GIF89a\x21\xf9\x04\x00\x0a\x00\x00\x00\x21\xf9\x04\x00\x19\x00\x00\x00")

    class FakePhotoImage:
        count = 0

        def __init__(self, *, file, format=None):
            if format is not None and FakePhotoImage.count >= 2:
                raise tk.TclError("no more frames")
            FakePhotoImage.count += 1

    monkeypatch.setattr("companion.window.tk.PhotoImage", FakePhotoImage)
    asset = AnimatedAsset(gif, clock=lambda: 0.0)

    assert len(asset.frames) == 2
    assert asset.durations == [0.1, 0.25]


def test_animated_asset_advances_when_frame_duration_elapses(monkeypatch, tmp_path):
    gif = tmp_path / "animated.gif"
    gif.write_bytes(b"GIF89a\x21\xf9\x04\x00\x0a\x00\x00\x00\x21\xf9\x04\x00\x19\x00\x00\x00")

    class FakePhotoImage:
        count = 0

        def __init__(self, *, file, format=None):
            if format is not None and FakePhotoImage.count >= 2:
                raise tk.TclError("no more frames")
            FakePhotoImage.count += 1

    monkeypatch.setattr("companion.window.tk.PhotoImage", FakePhotoImage)
    asset = AnimatedAsset(gif, clock=lambda: 0.0)

    asset.advance(now=0.09)
    assert asset.index == 0
    asset.advance(now=0.1)
    assert asset.index == 1
    asset.advance(now=0.35)
    assert asset.index == 0


def test_animated_asset_reset_restarts_timing(monkeypatch, tmp_path):
    gif = tmp_path / "animated.gif"
    gif.write_bytes(b"GIF89a\x21\xf9\x04\x00\x0a\x00\x00\x00\x21\xf9\x04\x00\x19\x00\x00\x00")

    class FakePhotoImage:
        count = 0

        def __init__(self, *, file, format=None):
            if format is not None and FakePhotoImage.count >= 2:
                raise tk.TclError("no more frames")
            FakePhotoImage.count += 1

    monkeypatch.setattr("companion.window.tk.PhotoImage", FakePhotoImage)
    now = [0.0]
    asset = AnimatedAsset(gif, clock=lambda: now[0])
    asset.advance(now=0.1)
    assert asset.index == 1
    now[0] = 1.0
    asset.reset()
    assert asset.index == 0
    asset.advance(now=1.05)
    assert asset.index == 0


def test_static_image_asset_has_one_frame(monkeypatch, tmp_path):
    image = tmp_path / "static.png"
    image.write_bytes(b"not a real png")

    class FakePhotoImage:
        def __init__(self, *, file, format=None):
            assert format is None

    monkeypatch.setattr("companion.window.tk.PhotoImage", FakePhotoImage)
    asset = AnimatedAsset(image, clock=lambda: 0.0)

    assert len(asset.frames) == 1
    asset.advance(now=100.0)
    assert asset.index == 0
