"""Optional OS notification adapter. Local only, no network, best-effort."""

from __future__ import annotations


def notify(title: str, message: str) -> bool:
    """Show a local OS notification. Returns True if one backend worked."""
    text = message.strip()
    if not text:
        return False
    heading = title.strip() or "Companion"
    try:
        from plyer import notification as plyer_notification  # type: ignore[import-not-found]

        plyer_notification.notify(title=heading, message=text, timeout=8)
        return True
    except Exception:
        pass
    try:
        from windows_toasts import Toast, WindowsToaster  # type: ignore[import-not-found]

        toaster = WindowsToaster(heading)
        toaster.show_toast(Toast((heading, text)))
        return True
    except Exception:
        pass
    return False
