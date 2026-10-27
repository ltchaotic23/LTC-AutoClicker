"""
In-Memory Transient GUI Error Reporter for LTC AutoClicker.

Catches unhandled exceptions and displays a native Windows on-screen error dialog
so users can view or screenshot the error without writing ANY files or diagnostic logs
to disk. Protects user privacy with zero disk footprint.
"""

import os
import sys
import threading
import traceback
from typing import Optional, Any

_INSTALLED = False

# Errors already shown this session, so a failing recurring timer can't open endless modal dialogs
_SHOWN_ERRORS = set()
_SHOWN_LOCK = threading.Lock()


def sanitize_text(text: str) -> str:
    """Sanitize absolute user directory paths from in-memory tracebacks to protect user privacy."""
    try:
        user_home = os.path.expanduser("~")
        if user_home:
            text = text.replace(user_home, "%USERPROFILE%")
            text = text.replace(user_home.replace("\\", "/"), "%USERPROFILE%")
        user_name = os.environ.get("USERNAME")
        if user_name:
            text = text.replace(f"\\Users\\{user_name}", "\\Users\\%USERNAME%")
            text = text.replace(f"/Users/{user_name}", "/Users/%USERNAME%")
    except Exception:
        pass
    return text


def format_error_details(exc_type: Any, exc_value: Any, exc_tb: Any, context: str = "Unhandled Exception") -> str:
    """Format a clean, concise, in-memory diagnostic message with sanitized file paths."""
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
    raw_tb = "".join(tb_lines).strip()
    sanitized_tb = sanitize_text(raw_tb)

    exc_name = getattr(exc_type, "__name__", str(exc_type))
    msg = (
        f"LTC AutoClicker encountered an unexpected error.\n\n"
        f"Context: {context}\n"
        f"Error: {exc_name}: {exc_value}\n\n"
        f"Traceback:\n{sanitized_tb}\n\n"
        f"--------------------------------------------------\n"
        f"[Zero-Disk Notice: No crash logs or files were written to disk. "
        f"You may screenshot this alert if submitting a bug report.]"
    )
    return msg


def show_error_dialog(exc_type: Any, exc_value: Any, exc_tb: Any, context: str = "Unhandled Exception") -> None:
    """Display an in-memory native Windows error dialog with zero disk writes."""
    msg = format_error_details(exc_type, exc_value, exc_tb, context)

    # Output to stderr if running attached to a terminal/console
    try:
        sys.stderr.write(msg + "\n")
        sys.stderr.flush()
    except Exception:
        pass

    signature = (context, "".join(traceback.format_exception_only(exc_type, exc_value)))
    with _SHOWN_LOCK:
        if signature in _SHOWN_ERRORS:
            return
        _SHOWN_ERRORS.add(signature)

    # Native Win32 MessageBoxW (works even if Tkinter event loop has crashed)
    try:
        import ctypes
        # 0x10 = MB_ICONERROR | MB_OK
        ctypes.windll.user32.MessageBoxW(0, msg, "LTC AutoClicker — Unexpected Error", 0x10)
        return
    except Exception:
        pass

    # Fallback to Tkinter messagebox if Win32 API is unavailable
    try:
        from tkinter import messagebox
        messagebox.showerror("LTC AutoClicker — Unexpected Error", msg)
    except Exception:
        pass


def _sys_excepthook(exc_type, exc_value, exc_tb):
    """Global hook for main thread unhandled exceptions."""
    show_error_dialog(exc_type, exc_value, exc_tb, context="Main Thread Exception")
    try:
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    except Exception:
        pass


def _threading_excepthook(args):
    """Global hook for worker thread unhandled exceptions."""
    show_error_dialog(
        args.exc_type,
        args.exc_value,
        args.exc_traceback,
        context=f"Thread '{getattr(args.thread, 'name', 'worker')}' Exception"
    )


def install_crash_handler(app_instance=None):
    """Install in-memory global exception hooks."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    sys.excepthook = _sys_excepthook
    threading.excepthook = _threading_excepthook

    if app_instance is not None:
        hook_tkinter_exceptions(app_instance)


def hook_tkinter_exceptions(tk_app):
    """Hook report_callback_exception on a Tk / CTk root instance."""
    def _tk_callback_exception(exc_type, exc_value, exc_tb):
        show_error_dialog(exc_type, exc_value, exc_tb, context="Tkinter Event/Timer Callback")

    tk_app.report_callback_exception = _tk_callback_exception
