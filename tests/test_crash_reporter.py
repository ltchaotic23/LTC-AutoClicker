import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from src.crash_reporter import write_crash_report, hook_tkinter_exceptions


class TestCrashReporter(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_write_crash_report(self):
        """Verify crash report writes valid diagnostic files containing traceback and thread dump."""
        with patch("src.crash_reporter.get_crash_dir", return_value=self.temp_dir.name):
            try:
                raise ValueError("Simulated testing explosion")
            except ValueError as e:
                exc_type, exc_val, exc_tb = sys.exc_info()
                log_path = write_crash_report(exc_type, exc_val, exc_tb, context="Unit Test Checkpoint")

            self.assertTrue(os.path.exists(log_path))
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn("LTC AUTOCLICKER", content)
            self.assertIn("CRASH REPORT", content)
            self.assertIn("Context: Unit Test Checkpoint", content)
            self.assertIn("Simulated testing explosion", content)
            self.assertIn("THREAD DUMP:", content)

    def test_path_sanitization_and_pruning(self):
        """Verify that absolute user paths are sanitized and old logs pruned."""
        from src.crash_reporter import _sanitize_text, _prune_old_reports
        user_name = os.environ.get("USERNAME", "testuser")
        fake_traceback = f'File "C:\\Users\\{user_name}\\Projects\\app\\main.py", line 12\n'
        sanitized = _sanitize_text(fake_traceback)
        self.assertNotIn(f"\\Users\\{user_name}", sanitized)
        self.assertIn("%", sanitized)

        # Verify native_fault.log rotation when oversized
        fault_log = os.path.join(self.temp_dir.name, "native_fault.log")
        with open(fault_log, "wb") as f:
            f.write(b"X" * (300 * 1024))  # 300KB
        _prune_old_reports(self.temp_dir.name, max_keep=5)
        self.assertFalse(os.path.exists(fault_log))
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir.name, "native_fault.log.1")))

    def test_hook_tkinter_exceptions(self):
        """Verify hook_tkinter_exceptions routes callbacks through write_crash_report."""
        mock_app = MagicMock()
        hook_tkinter_exceptions(mock_app)
        self.assertTrue(hasattr(mock_app, "report_callback_exception"))

        with patch("src.crash_reporter.write_crash_report") as mock_write:
            mock_app.report_callback_exception(KeyError, KeyError("missing_key"), None)
            self.assertTrue(mock_write.called)
            self.assertEqual(mock_write.call_args[1]["context"], "Tkinter Event/Timer Callback")


if __name__ == "__main__":
    unittest.main()
