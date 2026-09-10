from pathlib import Path

from companion.window import AnimatedAsset, DesktopWindow


def test_window_module_exports_gui_types():
    assert AnimatedAsset is not None
    assert DesktopWindow is not None
