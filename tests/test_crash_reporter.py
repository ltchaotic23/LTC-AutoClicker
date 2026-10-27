import os
import sys
import unittest
from unittest.mock import patch, MagicMock

from src.crash_reporter import (
    format_error_details,
    sanitize_text,
    show_error_dialog,
    hook_tkinter_exceptions,
)


class TestCrashReporter(unittest.TestCase):
    def test_format_error_details_and_sanitization(self):
        """Verify error formatting produces sanitized in-memory details with zero disk writes."""
        user_name = os.environ.get("USERNAME", "testuser")
        try:
            raise ValueError("Simulated testing explosion")
        except ValueError as e:
            exc_type, exc_val, exc_tb = sys.exc_info()
            msg = format_error_details(exc_type, exc_val, exc_tb, context="Unit Test Checkpoint")

        self.assertIn("LTC AutoClicker", msg)
        self.assertIn("ValueError", msg)
        self.assertIn("Simulated testing explosion", msg)
        self.assertIn("Context: Unit Test Checkpoint", msg)
        self.assertIn("Zero-Disk Notice", msg)

        # Verify username is not leaked if user path was in traceback
        fake_path_text = f"File 'C:\\Users\\{user_name}\\Projects\\main.py', line 10"
        sanitized = sanitize_text(fake_path_text)
        self.assertNotIn(f"\\Users\\{user_name}", sanitized)
        self.assertIn("%", sanitized)

    def test_show_error_dialog_invokes_win32_messagebox(self):
        """Verify show_error_dialog invokes Win32 MessageBoxW with error icon and zero disk activity."""
        with patch("ctypes.windll.user32.MessageBoxW") as mock_msgbox:
            show_error_dialog(RuntimeError, RuntimeError("Mock error"), None, context="Test Context")
            self.assertTrue(mock_msgbox.called)
            args = mock_msgbox.call_args[0]
            # args: (hwnd, text, title, uType)
            self.assertEqual(args[0], 0)
            self.assertIn("Mock error", args[1])
            self.assertEqual(args[2], "LTC AutoClicker — Unexpected Error")
            self.assertEqual(args[3], 0x10)  # MB_ICONERROR | MB_OK

    def test_repeated_error_shows_one_dialog(self):
        """A recurring identical error (e.g. from a timer) must not open endless modal dialogs."""
        with patch("ctypes.windll.user32.MessageBoxW") as mock_msgbox:
            for _ in range(5):
                show_error_dialog(ValueError, ValueError("Recurring timer failure"), None, context="Repeat Test")
            show_error_dialog(ValueError, ValueError("A different failure"), None, context="Repeat Test")
            self.assertEqual(mock_msgbox.call_count, 2)

    def test_hook_tkinter_exceptions(self):
        """Verify hook_tkinter_exceptions routes callbacks through show_error_dialog."""
        mock_app = MagicMock()
        hook_tkinter_exceptions(mock_app)
        self.assertTrue(hasattr(mock_app, "report_callback_exception"))

        with patch("src.crash_reporter.show_error_dialog") as mock_show:
            mock_app.report_callback_exception(KeyError, KeyError("missing_key"), None)
            self.assertTrue(mock_show.called)
            self.assertEqual(mock_show.call_args[1]["context"], "Tkinter Event/Timer Callback")


if __name__ == "__main__":
    unittest.main()
