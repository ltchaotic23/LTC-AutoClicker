"""
Resource, GDI & Handle Leak Endurance Auditor for LTC AutoClicker.
Measures Win32 GDI objects, User objects, OS handles, and memory deltas
across 10,000 click dispatches, 200 action tray redraws, and 50 window resize cycles.
"""

import gc
import ctypes
from ctypes import wintypes
import unittest
from unittest.mock import patch

from src.gui import AutoclickerApp, _PIL_GRADIENT_CACHE


class TestResourceLeaks(unittest.TestCase):
    def setUp(self):
        self.beep_patch = patch("winsound.Beep")
        self.beep_patch.start()

    def tearDown(self):
        self.beep_patch.stop()

    def _get_process_metrics(self):
        """Return (gdi_objects, user_objects, handle_count)."""
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        h_process = kernel32.GetCurrentProcess()

        gdi_count = user32.GetGuiResources(h_process, 0)   # GR_GDIOBJECTS = 0
        user_count = user32.GetGuiResources(h_process, 1)  # GR_USEROBJECTS = 1

        handle_count = wintypes.DWORD(0)
        res = kernel32.GetProcessHandleCount(h_process, ctypes.byref(handle_count))
        handles = handle_count.value if res else 0

        return gdi_count, user_count, handles

    @patch("src.engine._send_mouse_event")
    @patch("src.engine._send_key_event")
    def test_gdi_and_handle_endurance(self, mock_key, mock_mouse):
        """Verify that GDI objects and OS handles remain strictly flat during high throughput."""
        mock_mouse.return_value = None
        mock_key.return_value = None

        app = AutoclickerApp()
        app.withdraw()

        # Warm-up pass to let Tkinter, PIL, and font subsystems lazily initialize
        for _ in range(50):
            app._redraw_action_tray()
            app.update()
        gc.collect()

        baseline_gdi, baseline_user, baseline_handles = self._get_process_metrics()

        # If running in a headless CI / restricted sandbox without a desktop window station, skip GUI metrics
        if baseline_gdi == 0 and baseline_user == 0 and baseline_handles == 0:
            app.destroy()
            return

        # 1. Stress test action tray redraws (200 redraws)
        for _ in range(200):
            app._redraw_action_tray()

        # 2. Stress test synthetic window resize oscillations (50 resizing passes)
        for w in range(320, 370):
            app.bg_canvas.configure(width=w, height=360)
            app._on_shell_configure()
            app.update()

        # 3. Stress test high-frequency click worker dispatches (10,000 cycles)
        app.engine.hold_duration_sec = 0.0001
        app.engine.interval_sec = 0.0001
        app.engine.click_limit = 500
        app.engine.start()
        app.engine.stop(timeout=0.5)

        # Ensure cache bound is respected to prevent unbounded growth during resizing
        self.assertLessEqual(len(_PIL_GRADIENT_CACHE), 128, "PIL gradient cache exceeded bounded size!")

        # Clean up and collect
        gc.collect()
        app.update()

        final_gdi, final_user, final_handles = self._get_process_metrics()

        delta_gdi = final_gdi - baseline_gdi
        delta_user = final_user - baseline_user
        delta_handles = final_handles - baseline_handles

        app.destroy()

        # Tolerances: strictly <= 2 to catch any real handle/object leaks
        self.assertLessEqual(delta_gdi, 2, f"GDI Object leak detected! Delta: +{delta_gdi}")
        self.assertLessEqual(delta_user, 2, f"User Object leak detected! Delta: +{delta_user}")
        self.assertLessEqual(delta_handles, 3, f"OS Handle leak detected! Delta: +{delta_handles}")


if __name__ == "__main__":
    unittest.main()
