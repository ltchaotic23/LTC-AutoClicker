# LTC AutoClicker

A high-performance Windows desktop autoclicker utility built with Python, CustomTkinter, and native Win32 `SendInput` APIs.

## Current Version: v2.0

The active source code of LTC AutoClicker is located in [`LTC-AutoClicker-v2/`](./LTC-AutoClicker-v2/):
- **Standalone Portable Binary**: Can be run directly from any directory without installation.
- **Optional Start Menu Integration**: Can be installed to `%LOCALAPPDATA%\Programs\LTC-AutoClicker\` with a canonical Windows Start Menu shortcut by running `python build.py --install`.
- **Features**: Frameless metallic dark greyscale shell, glass-inspired inset caption buttons, 8-direction edge-drag resizing, high-speed Win32 clicking (CPS / ms), Key Presser mode, Lock Target Position (`Pick X, Y`), Self-Click Protection, central scatter, slow presets, and bezel counter/pin controls.

See [`LTC-AutoClicker-v2/README.md`](./LTC-AutoClicker-v2/README.md) for full development, configuration, testing, and build documentation.

---

## Privacy & Input Transparency

- **No Keylogging**: Hotkey detection uses the native Windows `GetAsyncKeyState` API **strictly** to query the physical up/down state of the single user-configured hotkey and the emergency `Pause` break key. The application does not monitor general typing, capture passwords, or log typed text.
- **Local-Only Operation**: LTC AutoClicker contains **zero network, telemetry, or analytics transmission code**. No data ever leaves your computer.
- **Local Configuration & Stored Fields**:
  Settings are persisted locally in plaintext JSON at `%LOCALAPPDATA%\AutoClicker-LTC\config.json`. The exact fields and default values stored are strictly limited to your operational preferences:
  - `active_mode`: Active tool mode (default `"clicker"`, or `"key_presser"`).
  - `speed_val`, `speed_unit`: Speed value and unit (default `100.0`, `"ms"` or `"CPS"`).
  - `click_interval_ms`, `target_cps`: Calculated interval and rate (default `100`, `10.0`).
  - `mouse_button`, `click_type`: Mouse button (`"left"`, `"right"`, `"middle"`) and click type (`"single"`, `"double"`).
  - `hotkey`, `hotkey_vk`: Activation key name and Win32 virtual-key code (default `"F6"`, `0x75`).
  - `target_key`, `target_key_vk`: Repeated key in Key Presser mode (default `"Space"`, `0x20`).
  - `trigger_mode`: Activation behavior (default `"toggle"`, or `"hold"`).
  - `click_limit`: Repeat limit before auto-stopping (default `0` = infinite).
  - `hold_duration_ms`: Key/button down-to-up duration (default `15` ms).
  - `panic_corner`: Emergency stop when cursor touches top-left screen corner (default `true`).
  - `lock_cursor_pos`, `locked_x`, `locked_y`: Screen targeting coordinates (default `false`, `-1`, `-1` = unassigned).
  - `window_x`, `window_y`: Desktop window coordinates for session restoration (default `-1`, `-1` = OS default).
  - Safety & feature flags: `self_click_protection` (`true`), `sound_enabled` (`true`), `jitter` (`false`), `pin_top` (`false`), `central_scatter` (`false`), `slow_presets` (`false`), `slow_preset_choice` (`"fast"`).
  
  *All local data can be instantly wiped by clicking **Reset Defaults** in the app or deleting the `%LOCALAPPDATA%\AutoClicker-LTC\` folder.*
- **Diagnostic Crash Logs**:
  Diagnostic logs are written exclusively to `%LOCALAPPDATA%\AutoClicker-LTC\crash_reports\`, automatically redact user profile usernames, and keep only the 5 most recent crash files. Native fault logs are capped at 256 KB.

---

## Disclaimer & Responsible Use

LTC AutoClicker is designed for productivity, accessibility, and software automation testing. Using automated input utilities in certain online multiplayer games or third-party services may violate their Terms of Service (ToS) or trigger automated detection systems. Use responsibly and at your own discretion.
