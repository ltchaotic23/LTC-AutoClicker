"""
Crash Reporter and Telemetry Layer for LTC AutoClicker.
Captures unhandled exceptions across main thread, worker threads, Tkinter callbacks,
and native C-level fault signals into %LOCALAPPDATA%\\AutoClicker-LTC\\crash_reports\\.
"""

import os
import sys
import threading
import traceback
import datetime
import faulthandler
from typing import Optional, Any

_INSTALLED = False
_CRASH_DIR: Optional[str] = None


def get_crash_dir() -> str:
    """Return the crash reports directory in %LOCALAPPDATA%\\AutoClicker-LTC\\crash_reports."""
    global _CRASH_DIR
    if _CRASH_DIR:
        return _CRASH_DIR
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        base = os.path.join(local_app, "AutoClicker-LTC", "crash_reports")
    else:
        base = os.path.join(os.path.expanduser("~"), ".autoclicker_ltc_crashes")
    os.makedirs(base, exist_ok=True)
    _CRASH_DIR = base
    return _CRASH_DIR


def write_crash_report(exc_type: Any, exc_value: Any, exc_tb: Any, context: str = "Unhandled Exception") -> str:
    """Format and write a detailed diagnostic crash report to disk."""
    try:
        crash_dir = get_crash_dir()
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(crash_dir, f"crash_{timestamp}_{os.getpid()}.log")

        lines = [
            "=" * 70,
            f"LTC AUTOCLICKER CRASH REPORT - {datetime.datetime.now().isoformat()}",
            "=" * 70,
            f"Context: {context}",
            f"Python Version: {sys.version}",
            f"Platform: {sys.platform}",
            f"PID: {os.getpid()}",
            f"Active Threads: {threading.active_count()}",
            "-" * 70,
            "THREAD DUMP:",
        ]

        for th in threading.enumerate():
            lines.append(f"  - Thread ID: {th.ident}, Name: {th.name}, Daemon: {th.daemon}, Alive: {th.is_alive()}")

        lines.extend([
            "-" * 70,
            "EXCEPTION TRACEBACK:",
            "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
            "=" * 70,
        ])

        report_content = "\n".join(lines)
        with open(report_path, "w", encoding="utf-8", errors="replace") as f:
            f.write(report_content)

        return report_path
    except Exception as report_err:
        try:
            sys.stderr.write(f"[Fatal] Failed to write crash report: {report_err}\n")
        except Exception:
            pass
        return ""


def _sys_excepthook(exc_type, exc_value, exc_tb):
    """Global hook for main thread unhandled exceptions."""
    write_crash_report(exc_type, exc_value, exc_tb, context="Main Thread Exception")
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def _threading_excepthook(args):
    """Global hook for worker thread unhandled exceptions."""
    write_crash_report(args.exc_type, args.exc_value, args.exc_traceback, context=f"Thread '{args.thread.name}' Exception")


def install_crash_handler(app_instance=None):
    """Install all global crash hooks and enable faulthandler."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    # 1. Main thread and worker thread hooks
    sys.excepthook = _sys_excepthook
    threading.excepthook = _threading_excepthook

    # 2. Native fault handler (captures hard 0xC0000005 access violations)
    try:
        crash_dir = get_crash_dir()
        fault_log_path = os.path.join(crash_dir, "native_fault.log")
        fault_file = open(fault_log_path, "a", encoding="utf-8", errors="replace")
        faulthandler.enable(file=fault_file, all_threads=True)
    except Exception:
        pass

    # 3. Hook Tkinter / CustomTkinter callback exception handler if app instance provided
    if app_instance is not None:
        hook_tkinter_exceptions(app_instance)


def hook_tkinter_exceptions(tk_app):
    """Hook report_callback_exception on a Tk / CTk root instance."""
    def _tk_callback_exception(exc_type, exc_value, exc_tb):
        write_crash_report(exc_type, exc_value, exc_tb, context="Tkinter Event/Timer Callback")
        try:
            sys.stderr.write("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
        except Exception:
            pass

    tk_app.report_callback_exception = _tk_callback_exception
