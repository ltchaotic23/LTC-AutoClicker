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
            "active_mode", "speed_unit", "click_interval_ms", "target_cps",
            "mouse_button", "click_type", "jitter", "hotkey", "trigger_mode",
            "always_on_top", "click_limit", "hold_duration_ms",
            "panic_corner", "central_scatter", "slow_presets",
            "slow_preset_choice"
        ]
        for key in expected_keys:
            self.assertIn(key, DEFAULT_CONFIG)

    def test_load_nonexistent_returns_defaults(self):
        """Loading when no file exists returns factory defaults."""
        cfg = self.mgr.load()
        self.assertEqual(cfg["hotkey"], "F6")
        self.assertEqual(cfg["click_interval_ms"], 100)
        self.assertEqual(cfg["trigger_mode"], "toggle")
        self.assertTrue(cfg["panic_corner"])

    def test_save_and_reload(self):
        """Saving custom values and reloading preserves them."""
        custom_cfg = dict(DEFAULT_CONFIG)
        custom_cfg["hotkey"] = "F8"
        custom_cfg["click_interval_ms"] = 50
        custom_cfg["trigger_mode"] = "hold"
        custom_cfg["click_limit"] = 250
        custom_cfg["hold_duration_ms"] = 30
        custom_cfg["panic_corner"] = False

        self.assertTrue(self.mgr.save(custom_cfg))
        reloaded = self.mgr.load()
        self.assertEqual(reloaded["hotkey"], "F8")
        self.assertEqual(reloaded["click_interval_ms"], 50)
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

    def test_invalid_key_codes_reset(self):
        """Hand-edited key codes the in-app binder can't produce fall back to defaults."""
        for bad_vk in (0x01, 0x02, 0x13, 0, 300, -5):
            custom_cfg = dict(DEFAULT_CONFIG)
            custom_cfg["hotkey"] = "LButton"
            custom_cfg["hotkey_vk"] = bad_vk
            custom_cfg["target_key"] = "Weird"
            custom_cfg["target_key_vk"] = bad_vk
            self.mgr.save(custom_cfg)

            cfg = self.mgr.load()
            self.assertEqual((cfg["hotkey"], cfg["hotkey_vk"]), ("F6", 0x75))
            self.assertEqual((cfg["target_key"], cfg["target_key_vk"]), ("Space", 0x20))

        # Mouse side buttons remain valid hotkeys
        custom_cfg = dict(DEFAULT_CONFIG)
        custom_cfg["hotkey"] = "Mouse 4"
        custom_cfg["hotkey_vk"] = 0x05
        self.mgr.save(custom_cfg)
        self.assertEqual(self.mgr.load()["hotkey_vk"], 0x05)

    def test_mid_click_hotkey_with_middle_button(self):
        """Mid Click hotkey + middle-button clicking would stop itself, so the button falls back to left."""
        custom_cfg = dict(DEFAULT_CONFIG)
        custom_cfg["hotkey"] = "Mid Click"
        custom_cfg["hotkey_vk"] = 0x04
        custom_cfg["mouse_button"] = "middle"
        self.mgr.save(custom_cfg)

        cfg = self.mgr.load()
        self.assertEqual(cfg["hotkey_vk"], 0x04)
        self.assertEqual(cfg["mouse_button"], "left")

    def test_path_isolation(self):
        """Default path must be inside AppData/local and NOT in the application working dir."""
        default_mgr = ConfigManager()
        path = default_mgr.config_path.lower()
        self.assertTrue("appdata" in path or ".autoclicker" in path)
        # Verify it is not a relative file in the current project root
        self.assertNotEqual(default_mgr.config_path, "config.json")


if __name__ == "__main__":
    unittest.main()
