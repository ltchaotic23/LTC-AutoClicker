import threading
import time
import unittest
from unittest.mock import patch

from src.engine import ClickEngine
from src.hotkey import HotkeyListener, VK_MAP

class TestClickEngine(unittest.TestCase):

    def test_initial_values(self):
        engine = ClickEngine()
        self.assertFalse(engine.is_running)
        self.assertEqual(engine.interval_sec, 0.100)
        self.assertEqual(engine.button, "left")
        self.assertEqual(engine.click_type, "single")
        self.assertEqual(engine.total_clicks, 0)
        self.assertEqual(engine.mode, "clicker")

    def test_flag_mapping(self):
        engine = ClickEngine()
        engine.button = "left"
        self.assertEqual(engine._get_flags(), (0x0002, 0x0004))
        engine.button = "right"
        self.assertEqual(engine._get_flags(), (0x0008, 0x0010))
        engine.button = "middle"
        self.assertEqual(engine._get_flags(), (0x0020, 0x0040))

    @patch("src.engine._send_mouse_event")
    def test_click_limit_and_counter(self, mock_send):
        engine = ClickEngine()
        engine.interval_sec = 0.010
        engine.click_limit = 5

        clicks = []
        engine.on_click_callback = lambda count: clicks.append(count)

        engine.start()
        start_t = time.time()
        while engine.is_running and time.time() - start_t < 1.0:
            time.sleep(0.01)

        self.assertFalse(engine.is_running)
        self.assertEqual(engine.total_clicks, 5)
        self.assertGreaterEqual(len(clicks), 1)
        self.assertEqual(clicks[-1], 5)
        self.assertTrue(mock_send.called)

    def test_slow_presets_intervals(self):
        engine = ClickEngine()
        # Default without slow presets
        engine.interval_sec = 0.250
        self.assertEqual(engine.get_effective_interval(), 0.250)

        # Enable slow presets
        engine.slow_presets = True
        engine.slow_preset_choice = "very_slow"
        self.assertEqual(engine.get_effective_interval(), 300.0)

        engine.slow_preset_choice = "slow"
        self.assertEqual(engine.get_effective_interval(), 60.0)

        engine.slow_preset_choice = "fast"
        self.assertEqual(engine.get_effective_interval(), 0.100)

    def test_central_scatter_spots(self):
        engine = ClickEngine()
        engine.central_scatter = True

        # Generate 16 consecutive positions (2 full 8-spot cycles)
        positions = [engine._get_next_scatter_pos() for _ in range(16)]
        self.assertEqual(len(positions), 16)

        # Coordinates should be positive and non-zero (within screen bounds)
        for x, y in positions:
            self.assertGreater(x, 0)
            self.assertGreater(y, 0)

        # First 8 positions should all be distinct (covering 8 different central spots)
        first_8 = positions[:8]
        # Allow small jitter but verify spread
        unique_zones = {(round(x / 30), round(y / 30)) for x, y in first_8}
        self.assertGreaterEqual(len(unique_zones), 6)

    def test_vk_map(self):
        self.assertIn("F6", VK_MAP)
        self.assertEqual(VK_MAP["F6"], 0x75)
        self.assertIn("XButton1 (Mouse 4)", VK_MAP)
        self.assertIn("Middle Click", VK_MAP)
        self.assertEqual(VK_MAP["Mouse 4"], 0x05)
        self.assertEqual(VK_MAP["Mouse 5"], 0x06)
        self.assertEqual(VK_MAP["Mid Click"], 0x04)

    @patch("src.engine._send_mouse_event")
    def test_self_click_protection_skips_click(self, mock_send):
        engine = ClickEngine()
        engine.interval_sec = 0.010
        engine.self_click_protection = True
        engine.protected_hwnd = 12345

        with patch.object(engine, "_is_cursor_over_protected_window", return_value=True):
            engine.start()
            time.sleep(0.05)
            engine.stop()

        self.assertEqual(engine.total_clicks, 0)
        self.assertFalse(mock_send.called)

    @patch("ctypes.windll.user32.SetCursorPos")
    @patch("src.engine._send_mouse_event")
    def test_lock_cursor_pos_and_elapsed_time(self, mock_send, mock_set_pos):
        engine = ClickEngine()
        engine.interval_sec = 0.010
        engine.click_limit = 2
        engine.lock_cursor_pos = True
        engine.locked_pos = (400, 300)

        engine.start()
        self.assertGreaterEqual(engine.get_session_elapsed(), 0.0)
        start_t = time.time()
        while engine.is_running and time.time() - start_t < 1.0:
            time.sleep(0.01)

        self.assertFalse(engine.is_running)
        self.assertEqual(engine.total_clicks, 2)
        mock_set_pos.assert_called_with(400, 300)
        self.assertEqual(engine.get_session_elapsed(), 0.0)

    @patch("src.engine._send_key_event")
    def test_key_presser_mode(self, mock_send_key):
        engine = ClickEngine()
        engine.mode = "key_presser"
        engine.target_key = "Backspace"
        engine.target_key_vk = 0x08
        engine.interval_sec = 0.010
        engine.click_limit = 3

        engine.start()
        start_t = time.time()
        while engine.is_running and time.time() - start_t < 1.0:
            time.sleep(0.01)

        self.assertFalse(engine.is_running)
        self.assertEqual(engine.total_clicks, 3)
        # 3 presses * 2 events (down + up) = 6 calls
        self.assertEqual(mock_send_key.call_count, 6)
        mock_send_key.assert_any_call(0x08, is_up=False)
        mock_send_key.assert_any_call(0x08, is_up=True)

    @patch("src.engine._send_key_event")
    def test_key_presser_pauses_while_app_has_focus(self, mock_send_key):
        """Key presses must not be typed into the Auto Clicker's own window."""
        engine = ClickEngine()
        engine.mode = "key_presser"
        engine.interval_sec = 0.010
        engine.protected_hwnd = 12345

        with patch("ctypes.windll.user32.GetForegroundWindow", return_value=12345):
            engine.start()
            time.sleep(0.05)
            engine.stop()

        self.assertEqual(engine.total_clicks, 0)
        self.assertFalse(mock_send_key.called)

        # Another window in the foreground: presses resume
        engine.click_limit = 2
        with patch("ctypes.windll.user32.GetForegroundWindow", return_value=99999):
            engine.start()
            start_t = time.time()
            while engine.is_running and time.time() - start_t < 1.0:
                time.sleep(0.01)
        self.assertEqual(engine.total_clicks, 2)

    def test_start_refuses_while_previous_worker_alive(self):
        """A worker that hasn't exited yet must not be revived alongside a new session."""
        engine = ClickEngine()
        release = threading.Event()
        stuck = threading.Thread(target=release.wait, daemon=True)
        stuck.start()
        engine._thread = stuck

        try:
            engine.start()
            self.assertFalse(engine.is_running)
            self.assertIs(engine._thread, stuck)
        finally:
            release.set()
            stuck.join(timeout=1.0)

if __name__ == "__main__":
    unittest.main()

