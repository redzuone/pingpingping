"""Apply dark title bar styling on Windows.

This module provides utilities to apply Windows 10/11 dark title bar styling
to Qt windows. On non-Windows platforms, the function is a no-op.
"""

import logging
import sys
from ctypes import byref, c_int, sizeof

from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)

# Only import Windows-specific modules on Windows
if sys.platform == 'win32':
    from ctypes import windll
else:
    windll = None


def apply_windows_dark_style(window: QWidget) -> None:
    """Apply dark title bar styling to a Qt window on Windows.

    This function applies DWM (Desktop Window Manager) attributes to enable
    dark title bar and dark borders on Windows 10/11+. On non-Windows platforms,
    this function does nothing.

    Args:
        window: The Qt main window to apply styling to.
    """
    if sys.platform != 'win32':
        return

    try:
        hwnd = _get_hwnd(window)
        if hwnd:
            _set_dwm_attribute(hwnd, 19, 1)  # DWMWA_USE_IMMERSIVE_DARK_MODE
            _set_dwm_attribute(hwnd, 20, 1)  # DWMWA_WINDOW_CORNER_PREFERENCE
            logger.debug(f'Applied dark title bar to window {hwnd}')
    except Exception as e:
        logger.warning(f'Failed to apply dark title bar: {e}')


def _set_dwm_attribute(hwnd: int, attrib: int, value: int) -> None:
    """Set a DWM attribute on a window.

    Args:
        hwnd: Window handle.
        attrib: Attribute id.
        value: Attribute value.
    """
    if windll is None:
        return
    try:
        windll.dwmapi.DwmSetWindowAttribute(
            hwnd, attrib, byref(c_int(value)), sizeof(c_int)
        )
    except OSError as e:
        raise OSError(f'DwmSetWindowAttribute failed: {e}') from e


def _get_hwnd(window: QWidget) -> int | None:
    """Get the native window handle (HWND) from a Qt window.

    Tries multiple methods to retrieve the handle, with fallback options
    for different window types and configurations.

    Args:
        window: The Qt widget.

    Returns:
        The window handle, or None if it could not be determined.
    """
    # Try Qt methods
    try:
        win_id = window.winId()
        return int(win_id)
    except (AttributeError, TypeError, ValueError):
        pass

    return None
