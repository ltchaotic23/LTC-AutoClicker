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
- **Local Configuration & Crash Data**:
  - Configuration is stored locally in `%LOCALAPPDATA%\AutoClicker-LTC\config.json` (click intervals, button type, target coordinate, and window position). You can wipe all stored data at any time via the in-app **Reset Defaults** button or by deleting the directory.
  - Diagnostic crash logs are written exclusively to `%LOCALAPPDATA%\AutoClicker-LTC\crash_reports\`, automatically redact user profile usernames, and keep only the 5 most recent logs.

---

## Disclaimer & Responsible Use

LTC AutoClicker is designed for productivity, accessibility, and software automation testing. Using automated input utilities in certain online multiplayer games or third-party services may violate their Terms of Service (ToS) or trigger automated detection systems. Use responsibly and at your own discretion.
