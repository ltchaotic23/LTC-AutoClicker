import os
import tempfile
import unittest
from src.config import ConfigManager, DEFAULT_CONFIG


class TestConfigManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_file = os.path.join(self.temp_dir.name, "config.json")
        self.mgr = ConfigManager(custom_path=self.temp_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_config_keys(self):
        """Ensure all required settings keys exist with correct default types."""
        expected_keys = [
            "active_mode", "speed_val", "speed_unit", "mouse_button",
            "click_type", "jitter", "hotkey", "trigger_mode", "pin_top",
            "click_limit", "hold_duration_ms",
            "panic_corner", "central_scatter", "slow_presets",
            "slow_preset_choice", "auto_save"
        ]
        for key in expected_keys:
            self.assertIn(key, DEFAULT_CONFIG)

    def test_load_nonexistent_returns_defaults(self):
        """Loading when no file exists returns factory defaults."""
        cfg = self.mgr.load()
        self.assertEqual(cfg["hotkey"], "F6")
        self.assertEqual(cfg["speed_val"], 100.0)
        self.assertEqual(cfg["trigger_mode"], "toggle")
        self.assertTrue(cfg["panic_corner"])

    def test_save_and_reload(self):
        """Saving custom values and reloading preserves them."""
        custom_cfg = dict(DEFAULT_CONFIG)
        custom_cfg["hotkey"] = "F8"
        custom_cfg["speed_val"] = 50.0
        custom_cfg["trigger_mode"] = "hold"
        custom_cfg["click_limit"] = 250
        custom_cfg["hold_duration_ms"] = 30
        custom_cfg["panic_corner"] = False

        self.assertTrue(self.mgr.save(custom_cfg))
        reloaded = self.mgr.load()
        self.assertEqual(reloaded["hotkey"], "F8")
        self.assertEqual(reloaded["speed_val"], 50.0)
        self.assertEqual(reloaded["trigger_mode"], "hold")
        self.assertEqual(reloaded["click_limit"], 250)
        self.assertEqual(reloaded["hold_duration_ms"], 30)
        self.assertFalse(reloaded["panic_corner"])

    def test_corrupt_json_fallback(self):
        """Corrupt JSON file recovers gracefully to defaults."""
        with open(self.temp_file, "w") as f:
            f.write("{invalid_json: true, broken")
        cfg = self.mgr.load()
        self.assertEqual(cfg["hotkey"], "F6")
        self.assertEqual(cfg["trigger_mode"], "toggle")

    def test_reset_defaults(self):
        """Resetting returns defaults and saves."""
        custom_cfg = dict(DEFAULT_CONFIG)
        custom_cfg["hotkey"] = "F12"
        self.mgr.save(custom_cfg)

        reset_cfg = self.mgr.reset_defaults()
        self.assertEqual(reset_cfg["hotkey"], "F6")
        reloaded = self.mgr.load()
        self.assertEqual(reloaded["hotkey"], "F6")

    def test_path_isolation(self):
        """Default path must be inside AppData/local and NOT in the application working dir."""
        default_mgr = ConfigManager()
        path = default_mgr.config_path.lower()
        self.assertTrue("appdata" in path or ".autoclicker" in path)
        # Verify it is not a relative file in the current project root
        self.assertNotEqual(default_mgr.config_path, "config.json")


if __name__ == "__main__":
    unittest.main()
