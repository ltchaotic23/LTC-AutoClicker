import os
import json
import math
from typing import Dict, Any, Optional

DEFAULT_CONFIG: Dict[str, Any] = {
    "active_mode": "clicker",
    "speed_unit": "ms",
    "speed_val": 100.0,
    "click_interval_ms": 100,
    "target_cps": 10.0,
    "mouse_button": "left",
    "click_type": "single",
    "jitter": False,
    "hotkey": "F6",
    "hotkey_vk": 0x75,
    "target_key": "Space",
    "target_key_vk": 0x20,
    "trigger_mode": "toggle",      # 'toggle' or 'hold'
    "pin_top": False,
    "always_on_top": False,
    "click_limit": 0,              # 0 = infinite
    "hold_duration_ms": 15,        # ms down-to-up separation
    "panic_corner": True,          # Small top-left screen region safety stop
    "central_scatter": False,      # 8-spot rotating central screen scatter
    "slow_presets": False,         # Experimental mode replacing custom speed with presets
    "slow_preset_choice": "fast",  # 'very_slow' (5m), 'slow' (1m), 'fast' (100ms)
    "auto_save": True,
    "sound_enabled": True,
    "self_click_protection": True, # Pause clicking while cursor is inside the app window
    "lock_cursor_pos": False,      # Lock clicks to a fixed screen coordinate
    "locked_x": -1,                # Fixed target X coordinate (-1 = capture at start)
    "locked_y": -1,                # Fixed target Y coordinate (-1 = capture at start)
    "window_x": -1,                # Last saved window X position (-1 = OS default)
    "window_y": -1,                # Last saved window Y position (-1 = OS default)
}


class ConfigManager:
    """Manages per-user application configuration stored in %LOCALAPPDATA%."""

    def __init__(self, custom_path: Optional[str] = None):
        self._path = custom_path or self._resolve_path()

    @property
    def config_path(self) -> str:
        return self._path

    def _resolve_path(self) -> str:
        """Resolve config file path in %LOCALAPPDATA% to ensure isolation per user."""
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata and os.path.isdir(local_appdata):
            app_dir = os.path.join(local_appdata, "AutoClicker-LTC")
        else:
            app_dir = os.path.join(os.path.expanduser("~"), ".autoclicker-ltc")
        return os.path.join(app_dir, "config.json")

    def load(self) -> Dict[str, Any]:
        """Load configuration from disk, falling back to defaults if missing or corrupted."""
        cfg = dict(DEFAULT_CONFIG)
        if not os.path.exists(self._path):
            return cfg

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                for k, v in saved.items():
                    if k not in cfg:
                        continue

                    def_val = DEFAULT_CONFIG[k]
                    def_type = type(def_val)

                    # Strict type checking (distinguish bool from int)
                    if def_type is bool:
                        if isinstance(v, bool):
                            cfg[k] = v
                    elif def_type is int:
                        if type(v) is int and not isinstance(v, bool):
                            cfg[k] = v
                    elif def_type is float:
                        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
                            cfg[k] = float(v)
                    elif def_type is str:
                        if isinstance(v, str):
                            cfg[k] = v

                # Enforce semantic bounds & valid enum sets
                cfg["click_interval_ms"] = max(1, min(3600000, int(cfg.get("click_interval_ms", 100))))
                cfg["target_cps"] = max(0.1, min(1000.0, float(cfg.get("target_cps", 10.0))))
                cfg["hold_duration_ms"] = max(1, min(10000, int(cfg.get("hold_duration_ms", 15))))
                cfg["click_limit"] = max(0, int(cfg.get("click_limit", 0)))

                if cfg.get("mouse_button") not in ("left", "right", "middle"):
                    cfg["mouse_button"] = "left"
                if cfg.get("click_type") not in ("single", "double"):
                    cfg["click_type"] = "single"
                if cfg.get("trigger_mode") not in ("toggle", "hold"):
                    cfg["trigger_mode"] = "toggle"
                if cfg.get("speed_unit") not in ("ms", "cps"):
                    cfg["speed_unit"] = "ms"
                if cfg.get("slow_preset_choice") not in ("very_slow", "slow", "fast"):
                    cfg["slow_preset_choice"] = "fast"
                if cfg.get("active_mode") not in ("clicker", "key_presser"):
                    cfg["active_mode"] = "clicker"
        except Exception:
            pass  # Fall back to defaults safely

        return cfg

    def save(self, config: Dict[str, Any]) -> bool:
        """Save configuration dictionary atomically using a temporary file."""
        tmp_path = None
        try:
            folder = os.path.dirname(self._path)
            if folder and not os.path.exists(folder):
                os.makedirs(folder, exist_ok=True)

            tmp_path = self._path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            os.replace(tmp_path, self._path)
            return True
        except Exception:
            if tmp_path is not None:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass
            return False

    def reset_defaults(self) -> Dict[str, Any]:
        """Reset config to factory defaults and save."""
        cfg = dict(DEFAULT_CONFIG)
        self.save(cfg)
        return cfg

    def reset(self) -> Dict[str, Any]:
        """Alias for reset_defaults."""
        return self.reset_defaults()
