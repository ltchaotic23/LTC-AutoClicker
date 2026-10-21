# LTC AutoClicker v2

A high-performance Windows desktop autoclicker utility built with Python, CustomTkinter, and native Win32 `SendInput` APIs, featuring a frameless metallic dark greyscale shell.

## What's New in v2.0.0

- **Frameless Metallic Shell**: Custom dark metallic greyscale bezel with subtle glass gradients and clean central card layout.
- **Built-in Caption Controls**: Custom glass-inspired inset minimize and close buttons rendered directly onto the top bezel.
- **Frameless Edge-Drag Resizing**: Full 8-direction mouse hit-testing on bezel borders for fluid resizing and borderless window dragging with native Windows taskbar presence.
- **Bezel Navigation & Footer**:
  - `Mini` / `Full` layout quick-toggle (`nav_mini`)
  - Settings drawer toggle (`nav_settings`)
  - Bottom bezel live Session Click / Cast counter (`footer_counter`) with instant reset (`footer_reset`)
  - Always-on-top toggle (`footer_pin`, `topmost_switch_var`)

## Features

- **High-Speed Clicking & Key Presser**: Custom millisecond intervals or Clicks Per Second (CPS) powered by the Win32 `SendInput` API, with hardware scan-code keyboard key repeating (`Space`, `E`, `Backspace`, `Enter`, etc.).
- **Button & Click Types**: Left, right, or middle mouse buttons; single or double clicking.
- **Global Hotkey & Safety Controls**:
  - Global hotkey listener (default **F6**, supports keyboard keys + `Mouse 4` / `Mouse 5` / `Mid Click`) with in-app key rebinding.
  - Emergency stops: dedicated **Pause** break key, top-left screen corner panic stop, and automatic **Self-Click Protection** when hovering over the app window.
  - Dual trigger modes: **Toggle** (start/stop) or **Hold Key** (active only while held).
- **Target Position Locking**: Lock clicks to a fixed `(X, Y)` coordinate with interactive on-screen `Pick (X, Y)` target selection.
- **Central Cursor Scatter**: 8-spot rotating cursor scatter around screen center.
- **Slow AFK Presets**: Experimental modes with 5-minute (Very Slow), 1-minute (Slow), and 100ms (Fast) presets.
- **Per-User Configuration**: Settings and window coordinates automatically persist across sessions in `%LOCALAPPDATA%\AutoClicker-LTC\config.json`.
- **Privacy & Security**: Native `GetAsyncKeyState` polling is strictly isolated to your configured hotkey and `Pause` emergency key. Zero background keystroke logging, zero telemetry, and zero network transmission.

## Run From Source

Install dependencies and launch the application:

```powershell
python -m pip install -r requirements.txt
python main.py
```

## Build & Installation

### 1. Compile Standalone Executable
Install developer dependencies and compile the portable Windows binary:

```powershell
python -m pip install -r requirements-dev.txt
python build.py
```

The compiled standalone executable will be output to `dist/LTC-AutoClicker.exe`.

### 2. Optional Local Installation
To compile and automatically register the application in `%LOCALAPPDATA%\Programs\LTC-AutoClicker\` with a canonical Windows Start Menu shortcut:

```powershell
python build.py --install
```

## Project Layout

```text
LTC-AutoClicker-v2/
├── assets/                           # Application icons (.ico and .png)
├── build.py                          # Standalone PyInstaller build script (outputs LTC-AutoClicker.exe)
├── LTC-AutoClicker.spec              # PyInstaller specification file
├── main.py                           # Application entry point
├── README.md                         # V2 Documentation
├── requirements.txt                  # Python dependencies
├── src/
│   ├── __init__.py                   # Package version metadata (v2.0.0)
│   ├── config.py                     # Per-user JSON settings manager (atomic persistence)
│   ├── crash_reporter.py             # Global telemetry & minidump-style crash reporter
│   ├── engine.py                     # Win32 SendInput click engine & timing loops
│   ├── gui.py                        # Frameless Aero shell & CustomTkinter UI
│   └── hotkey.py                     # Win32 global hotkey hook listener
└── tests/
    ├── test_config.py                # Configuration manager unit tests
    ├── test_crash_reporter.py        # Crash telemetry and exception hook tests
    ├── test_engine.py                # Click engine and timing tests
    ├── test_gui.py                   # UI lifecycle and bezel integration tests
    ├── test_fuzz_config.py           # 1,500-mutation fuzz and boundary stress tests
    ├── test_chaos_monkey.py          # 2,500-operation concurrent UI state chaos tests
    ├── test_resource_leaks.py        # Windows GDI object & OS handle leak audit tests
    └── test_job_object_starvation.py # Windows Job Object memory starvation tests
```
