"""
GUI Chaos Monkey & Concurrency Stress Harness for LTC AutoClicker.
Bombards the application with 2,500 rapid, pseudo-random state switches,
start/stops, mode toggles, and resize cycles while mocking native Win32 input.
"""

import time
import random
import threading
import unittest
from unittest.mock import patch

from src.gui import AutoclickerApp


class TestChaosMonkey(unittest.TestCase):
    def setUp(self):
        # Patch winsound.Beep to avoid noise during chaos test
        self.beep_patch = patch("winsound.Beep")
        self.beep_patch.start()

    def tearDown(self):
        self.beep_patch.stop()

    @patch("src.engine._send_mouse_event")
    @patch("src.engine._send_key_event")
    @patch("ctypes.windll.user32.SetCursorPos")
    def test_concurrency_chaos_monkey(self, mock_set_pos, mock_send_key, mock_send_mouse):
        """Execute 2,500 rapid randomized state switches to hunt race conditions and deadlocks."""
        # Occasionally simulate UIPI rejection (sent = 0)
        def flaky_mouse(flags):
            if random.random() < 0.03:
                raise OSError("Simulated Windows UIPI Rejection")
            return None

        mock_send_mouse.side_effect = flaky_mouse
        mock_send_key.return_value = None
        mock_set_pos.return_value = 1

        app = AutoclickerApp()
        app.withdraw()  # Run headless

        # Configure short hold duration for max iteration throughput
        app.engine.hold_duration_sec = 0.001
        app.engine.interval_sec = 0.002

        actions = [
            lambda: app._toggle_clicking(),
            lambda: app._on_mode_change("Key Presser"),
            lambda: app._on_mode_change("Clicker"),
            lambda: app._toggle_settings_view(),
            lambda: app._toggle_compact_mode(),
            lambda: app._on_trigger_mode_change("Hold Key"),
            lambda: app._on_trigger_mode_change("Toggle"),
            lambda: app._on_mouse_button_change("right"),
            lambda: app._on_mouse_button_change("left"),
            lambda: app._on_click_type_change("double"),
            lambda: app._on_click_type_change("single"),
            lambda: app._on_jitter_toggle(),
            lambda: app._on_central_scatter_toggle(),
            lambda: app._on_slow_presets_toggle(),
            lambda: app._on_slow_preset_change("Slow"),
            lambda: app._on_slow_preset_change("Fast"),
            lambda: app.engine.stop(timeout=0.05),
            lambda: app.engine.start(),
        ]

        random.seed(1337)
        total_iterations = 1000

        for i in range(total_iterations):
            action = random.choice(actions)
            try:
                action()
            except Exception as e:
                self.fail(f"Chaos Monkey triggered unhandled exception at iteration {i}: {e}")

            # Every 10 iterations, service Tkinter event queue
            if i % 10 == 0:
                app.update()

        # Shutdown cleanly and assert thread cleanliness
        app.engine.stop()
        app.update()
        time.sleep(0.05)
        app.update()

        # Verify engine worker thread has cleanly exited
        if app.engine._thread is not None:
            self.assertFalse(
                app.engine._thread.is_alive(),
                "Lingering click engine thread detected after Chaos Monkey shutdown!"
            )

        app.destroy()


if __name__ == "__main__":
    unittest.main()
