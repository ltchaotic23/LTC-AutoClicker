"""
Automated Config & Input Boundary Fuzzer for LTC AutoClicker.
Fuzzes ConfigManager and input boundary sanitization against malformed payloads,
corrupted JSON, type violations (bool-as-int), NaN/Inf, and extreme values.
"""

import os
import json
import random
import string
import tempfile
import unittest
from typing import Any

from src.config import ConfigManager, DEFAULT_CONFIG


class TestFuzzConfig(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.temp_dir.name, "config.json")
        self.mgr = ConfigManager(custom_path=self.config_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_bool_as_int_rejection(self):
        """Ensure Python's bool-is-subclass-of-int does not corrupt integer settings."""
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump({
                "click_interval_ms": False,
                "hotkey_vk": True,
                "click_limit": False,
                "hold_duration_ms": True,
            }, f)

        cfg = self.mgr.load()
        # Must retain defaults, not 0 or 1
        self.assertEqual(cfg["click_interval_ms"], DEFAULT_CONFIG["click_interval_ms"])
        self.assertEqual(cfg["hotkey_vk"], DEFAULT_CONFIG["hotkey_vk"])
        self.assertEqual(cfg["click_limit"], DEFAULT_CONFIG["click_limit"])
        self.assertEqual(cfg["hold_duration_ms"], DEFAULT_CONFIG["hold_duration_ms"])

    def test_nan_and_infinity_fuzz(self):
        """Ensure NaN, Inf, and -Inf are rejected in floating-point fields."""
        # Directly writing invalid float literals via raw text or extreme exponents
        raw_payloads = [
            '{"target_cps": 1e309}',   # Overflow to Infinity in JSON
            '{"target_cps": -1e309}',  # Overflow to -Infinity
            '{"target_cps": NaN}',
            '{"target_cps": Infinity}',
        ]
        for payload in raw_payloads:
            with open(self.config_path, "w", encoding="utf-8") as f:
                f.write(payload)

            cfg = self.mgr.load()
            self.assertTrue(0.1 <= cfg["target_cps"] <= 1000.0)

    def test_extreme_and_negative_boundaries(self):
        """Ensure negative intervals and extreme values are clamped to safe domains."""
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump({
                "click_interval_ms": -500,
                "target_cps": -99.9,
                "hold_duration_ms": -10,
                "click_limit": -100,
                "mouse_button": "invalid_banana_button",
                "click_type": "triple",
                "trigger_mode": "magic",
                "speed_unit": "lightyears",
                "slow_preset_choice": "quantum_speed",
                "active_mode": "fishing",  # Legacy/removed mode
            }, f)

        cfg = self.mgr.load()
        self.assertGreaterEqual(cfg["click_interval_ms"], 1)
        self.assertGreaterEqual(cfg["target_cps"], 0.1)
        self.assertGreaterEqual(cfg["hold_duration_ms"], 1)
        self.assertGreaterEqual(cfg["click_limit"], 0)
        self.assertIn(cfg["mouse_button"], ("left", "right", "middle"))
        self.assertIn(cfg["click_type"], ("single", "double"))
        self.assertIn(cfg["trigger_mode"], ("toggle", "hold"))
        self.assertIn(cfg["speed_unit"], ("ms", "cps"))
        self.assertIn(cfg["slow_preset_choice"], ("very_slow", "slow", "fast"))
        self.assertEqual(cfg["active_mode"], "clicker")  # Fallback from removed fishing

    def test_corrupted_json_garbage(self):
        """Ensure random byte and truncated text corruptions never raise exceptions."""
        corruptions = [
            b"",
            b"\x00\x00\x00\x00",
            b'{"active_mode": "clicker", "speed_unit": ',  # Truncated
            b"<!DOCTYPE html><html><body>Error 404</body></html>",
            b'{"key": [1, 2, 3}',  # Unclosed bracket
            b"{null: true}",
            b'{"locked_x": "not an int"}',
        ]
        for corrupt in corruptions:
            with open(self.config_path, "wb") as f:
                f.write(corrupt)

            cfg = self.mgr.load()
            self.assertEqual(cfg["active_mode"], "clicker")
            self.assertEqual(cfg["hotkey"], "F6")

    def test_mass_mutation_fuzz(self):
        """Feed 1,500 randomized mutated dictionaries to verify total parser stability."""
        random.seed(42)
        valid_keys = list(DEFAULT_CONFIG.keys())

        for i in range(1500):
            mutated = {}
            for _ in range(random.randint(1, len(valid_keys))):
                k = random.choice(valid_keys)
                mutation_type = random.randint(1, 6)
                if mutation_type == 1:
                    mutated[k] = None
                elif mutation_type == 2:
                    mutated[k] = random.choice([True, False, 0, 1, -1, 999999999, -999999999])
                elif mutation_type == 3:
                    mutated[k] = random.uniform(-1000.0, 1000.0)
                elif mutation_type == 4:
                    mutated[k] = "".join(random.choices(string.printable, k=random.randint(0, 50)))
                elif mutation_type == 5:
                    mutated[k] = [random.randint(0, 10) for _ in range(random.randint(0, 5))]
                else:
                    mutated[k] = {"nested": "junk"}

            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(mutated, f)

            cfg = self.mgr.load()
            self.assertIsInstance(cfg, dict)
            # Essential invariants
            self.assertIn("active_mode", cfg)
            self.assertIn(cfg["active_mode"], ("clicker", "key_presser"))
            self.assertGreaterEqual(cfg["click_interval_ms"], 1)

    def test_atomic_save(self):
        """Ensure save writes to temp file first and replaces atomically."""
        test_cfg = dict(DEFAULT_CONFIG)
        test_cfg["hotkey"] = "F11"
        self.assertTrue(self.mgr.save(test_cfg))
        self.assertFalse(os.path.exists(self.config_path + ".tmp"))
        self.assertTrue(os.path.exists(self.config_path))
        reloaded = self.mgr.load()
        self.assertEqual(reloaded["hotkey"], "F11")


if __name__ == "__main__":
    unittest.main()
