import ctypes
from ctypes import wintypes
import time
import random
import math
import threading
from typing import Callable, Optional, Tuple, List

# Win32 Constants
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
MAPVK_VK_TO_VSC = 0
EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E}

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class KeyBdInput(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class Input_I(ctypes.Union):
    _fields_ = [
        ("mi", MouseInput),
        ("ki", KeyBdInput),
        ("hi", HardwareInput),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("ii", Input_I),
    ]


def _send_mouse_event(flags: int):
    """Send low-level mouse event using Win32 SendInput."""
    extra = ULONG_PTR(0)
    ii_ = Input_I()
    ii_.mi = MouseInput(0, 0, 0, flags, 0, ctypes.addressof(extra))
    cmd = INPUT(INPUT_MOUSE, ii_)
    sent = ctypes.windll.user32.SendInput(1, ctypes.byref(cmd), ctypes.sizeof(cmd))
    if sent != 1:
        raise OSError("Windows did not accept the mouse input event")


def _send_key_event(vk_code: int, is_up: bool = False):
    """Send low-level keyboard event (with hardware scan code) using Win32 SendInput."""
    extra = ULONG_PTR(0)
    scan_code = ctypes.windll.user32.MapVirtualKeyW(int(vk_code), MAPVK_VK_TO_VSC) & 0xFFFF
    flags = KEYEVENTF_KEYUP if is_up else 0
    if int(vk_code) in EXTENDED_VKS:
        flags |= KEYEVENTF_EXTENDEDKEY
    ii_ = Input_I()
    ii_.ki = KeyBdInput(int(vk_code), scan_code, flags, 0, ctypes.addressof(extra))
    cmd = INPUT(INPUT_KEYBOARD, ii_)
    sent = ctypes.windll.user32.SendInput(1, ctypes.byref(cmd), ctypes.sizeof(cmd))
    if sent != 1:
        raise OSError("Windows did not accept the keyboard input event")


class ClickEngine:
    """Windows autoclicker and key presser engine."""

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

        # Operating Mode: 'clicker' or 'key_presser'
        self.mode: str = "clicker"

        # Standard Clicker & Key Presser parameters
        self.interval_sec: float = 0.100  # Default 100ms
        self.button: str = "left"        # 'left', 'right', 'middle'
        self.click_type: str = "single"  # 'single', 'double'
        self.target_key: str = "Space"   # Key Presser target key name
        self.target_key_vk: int = 0x20   # Key Presser virtual key code (default VK_SPACE)
        self.jitter_percent: float = 0.0  # 0.0 to 0.5 (e.g. 0.1 = +/- 10%)
        self.click_limit: int = 0        # 0 = infinite, >0 = stop after N clicks/presses
        self.total_clicks: int = 0
        self.hold_duration_sec: float = 0.015  # Default 15ms down/up hold duration
        self.panic_corner: bool = True         # (0, 0) screen corner safety stop

        # Quality-of-Life & Target Control
        self.self_click_protection: bool = True
        self.protected_hwnd: Optional[int] = None
        self.lock_cursor_pos: bool = False
        self.locked_pos: Optional[Tuple[int, int]] = None
        self._active_locked_pos: Optional[Tuple[int, int]] = None
        self.session_start_time: float = 0.0

        # Advanced Settings: Central Area Scatter (8 spots) & Slow Presets
        self.central_scatter: bool = False     # Rotate clicks across 8 central screen spots
        self._scatter_order: List[int] = []
        self._scatter_idx: int = 0
        self.slow_presets: bool = False        # Override custom speed with presets
        self.slow_preset_choice: str = "fast"  # 'very_slow' (5m), 'slow' (1m), 'fast' (100ms)

        # Callbacks
        self.on_click_callback: Optional[Callable[[int], None]] = None
        self.on_state_change: Optional[Callable[[bool], None]] = None
        self.on_countdown: Optional[Callable[[float], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

    @property
    def is_running(self) -> bool:
        return self._running

    def get_session_elapsed(self) -> float:
        """Return elapsed seconds for the current active session."""
        if not self._running or self.session_start_time <= 0.0:
            return 0.0
        return max(0.0, time.monotonic() - self.session_start_time)

    def start(self):
        """Start clicking or key pressing in background thread."""
        with self._lock:
            if self._running:
                return
            if self._thread and self._thread.is_alive():
                self._stop_event.set()
                self._thread.join(timeout=0.25)
            self._stop_event.clear()
            self._running = True
            self.session_start_time = time.monotonic()

            if self.lock_cursor_pos:
                if self.locked_pos and self.locked_pos[0] >= 0 and self.locked_pos[1] >= 0:
                    self._active_locked_pos = self.locked_pos
                else:
                    pt = wintypes.POINT()
                    if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
                        self._active_locked_pos = (pt.x, pt.y)
                    else:
                        self._active_locked_pos = None
            else:
                self._active_locked_pos = None

            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

        if self.on_state_change:
            self.on_state_change(True)

    def stop(self, timeout: float = 0.5):
        """Stop clicking or key pressing and wait for worker thread to terminate."""
        worker = None
        with self._lock:
            self._running = False
            self._stop_event.set()
            worker = self._thread

        if worker and worker.is_alive() and threading.current_thread() != worker:
            worker.join(timeout=timeout)

        if self.on_state_change:
            self.on_state_change(False)
        if self.on_countdown:
            self.on_countdown(0.0)

    def toggle(self) -> bool:
        """Toggle running state."""
        if self._running:
            self.stop()
            return False
        else:
            self.start()
            return True

    def reset_counter(self):
        """Reset total clicks/casts counter."""
        self.total_clicks = 0
        if self.on_click_callback:
            self.on_click_callback(0)

    def _get_flags(self, override_button: Optional[str] = None):
        """Map button name to down/up event flags."""
        b = (override_button or self.button).lower()
        if b == "right":
            return MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
        elif b == "middle":
            return MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP
        return MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP

    def _is_panic_corner(self) -> bool:
        """Check a small top-left screen region as an additional stop gesture."""
        if not self.panic_corner:
            return False
        try:
            pt = wintypes.POINT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
                return 0 <= pt.x <= 4 and 0 <= pt.y <= 4
        except Exception:
            pass
        return False

    def _is_point_over_protected_window(self, x: int, y: int) -> bool:
        """Return True if self-click protection is active and (x, y) is inside the app window."""
        if not self.self_click_protection or not self.protected_hwnd:
            return False
        try:
            user32 = ctypes.windll.user32
            if not user32.IsWindowVisible(self.protected_hwnd) or user32.IsIconic(self.protected_hwnd):
                return False
            rect = wintypes.RECT()
            if user32.GetWindowRect(self.protected_hwnd, ctypes.byref(rect)):
                return (rect.left <= x <= rect.right) and (rect.top <= y <= rect.bottom)
        except Exception:
            pass
        return False

    def _is_cursor_over_protected_window(self) -> bool:
        """Return True if self-click protection is active and cursor hovers over the app window."""
        if not self.self_click_protection or not self.protected_hwnd:
            return False
        try:
            pt = wintypes.POINT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
                return self._is_point_over_protected_window(pt.x, pt.y)
        except Exception:
            pass
        return False

    def _do_click(self, override_button: Optional[str] = None, hold_ms: Optional[float] = None):
        """Perform a single or double click with realistic press duration."""
        if self._stop_event.is_set():
            return False
        actual_hold = hold_ms if hold_ms is not None else self.hold_duration_sec
        down_flag, up_flag = self._get_flags(override_button)
        _send_mouse_event(down_flag)
        try:
            self._stop_event.wait(actual_hold)
        finally:
            try:
                _send_mouse_event(up_flag)
            except Exception:
                pass

        if self.mode == "clicker" and self.click_type == "double":
            if self._stop_event.wait(0.025):
                return True
            _send_mouse_event(down_flag)
            try:
                self._stop_event.wait(actual_hold)
            finally:
                try:
                    _send_mouse_event(up_flag)
                except Exception:
                    pass
        return True

    def _do_key_press(self, hold_ms: Optional[float] = None) -> bool:
        """Perform a single key press and release with realistic hold duration."""
        if self._stop_event.is_set():
            return False
        actual_hold = hold_ms if hold_ms is not None else self.hold_duration_sec
        vk = int(self.target_key_vk)
        _send_key_event(vk, is_up=False)
        try:
            self._stop_event.wait(actual_hold)
        finally:
            try:
                _send_key_event(vk, is_up=True)
            except Exception:
                pass
        return True

    def _wait_interruptible(self, duration: float):
        """Wait without spinning and wake promptly when Stop is requested."""
        if duration <= 0:
            return
        self._stop_event.wait(duration)

    def _run_loop(self):
        """Dispatch loop based on active mode."""
        try:
            if self.mode == "key_presser":
                self._key_loop()
            else:
                self._click_loop()
        except Exception as exc:
            self._running = False
            self._stop_event.set()
            if self.on_error:
                try:
                    self.on_error(str(exc))
                except Exception:
                    pass
            if self.on_state_change:
                self.on_state_change(False)
        finally:
            self._running = False
            self._stop_event.set()

    def get_effective_interval(self) -> float:
        """Return active interval taking slow presets into account."""
        if self.slow_presets:
            if self.slow_preset_choice == "very_slow":
                return 300.0  # 5 minutes
            elif self.slow_preset_choice == "slow":
                return 60.0   # 1 minute
            else:
                return 0.100  # fast standard default (100ms)
        return self.interval_sec

    def _get_next_scatter_pos(self) -> Tuple[int, int]:
        """Calculate next position in the 8-spot rotating central area sequence."""
        try:
            w = ctypes.windll.user32.GetSystemMetrics(0)
            h = ctypes.windll.user32.GetSystemMetrics(1)
            if w <= 0 or h <= 0:
                w, h = 1920, 1080
        except Exception:
            w, h = 1920, 1080

        cx, cy = w // 2, h // 2
        radius = int(min(w, h) * 0.07)  # ~75px radius on 1080p

        if len(self._scatter_order) == 0 or self._scatter_idx >= len(self._scatter_order):
            self._scatter_order = list(range(8))
            random.shuffle(self._scatter_order)
            self._scatter_idx = 0

        spot_num = self._scatter_order[self._scatter_idx]
        self._scatter_idx += 1

        # 8 radial angles: 0, 45, 90, 135, 180, 225, 270, 315 deg
        angle = spot_num * (2.0 * math.pi / 8.0)
        # Small organic jitter to avoid exact pixel repetition (+/- 10px)
        jitter_x = random.randint(-10, 10)
        jitter_y = random.randint(-10, 10)

        target_x = max(1, min(w - 2, int(cx + radius * math.cos(angle) + jitter_x)))
        target_y = max(1, min(h - 2, int(cy + radius * math.sin(angle) + jitter_y)))
        return target_x, target_y

    def _click_loop(self):
        """High-speed clicking execution loop with scatter, position lock, self-click guard, and countdown."""
        clicks_this_session = 0
        last_counter_update = 0.0
        while self._running:
            if self._is_panic_corner():
                self._running = False
                self._stop_event.set()
                if self.on_state_change:
                    self.on_state_change(False)
                break

            if self._is_cursor_over_protected_window():
                # Pause clicking while the user hovers over the Auto Clicker window
                self._wait_interruptible(min(0.04, max(0.01, self.get_effective_interval())))
                continue

            if self.central_scatter:
                tx, ty = self._get_next_scatter_pos()
                if self._is_point_over_protected_window(tx, ty):
                    self._wait_interruptible(min(0.04, max(0.01, self.get_effective_interval())))
                    continue
                try:
                    ctypes.windll.user32.SetCursorPos(tx, ty)
                    time.sleep(0.003)
                except Exception:
                    pass
            elif self.lock_cursor_pos and self._active_locked_pos:
                lx, ly = self._active_locked_pos
                if self._is_point_over_protected_window(lx, ly):
                    self._wait_interruptible(min(0.04, max(0.01, self.get_effective_interval())))
                    continue
                try:
                    ctypes.windll.user32.SetCursorPos(lx, ly)
                except Exception:
                    pass

            if not self._do_click():
                break
            self.total_clicks += 1
            clicks_this_session += 1

            now = time.monotonic()
            if self.on_click_callback and now - last_counter_update >= 0.05:
                try:
                    self.on_click_callback(self.total_clicks)
                    last_counter_update = now
                except Exception:
                    pass

            if self.click_limit > 0 and clicks_this_session >= self.click_limit:
                self._running = False
                self._stop_event.set()
                if self.on_click_callback:
                    try:
                        self.on_click_callback(self.total_clicks)
                    except Exception:
                        pass
                if self.on_state_change:
                    self.on_state_change(False)
                break

            # Calculate interval with optional jitter
            delay = self.get_effective_interval()
            if self.jitter_percent > 0 and not self.slow_presets:
                jitter_range = delay * self.jitter_percent
                delay += random.uniform(-jitter_range, jitter_range)
                delay = max(0.001, delay)

            if delay >= 1.0:
                # Responsive countdown loop for long intervals (slow presets)
                target_time = time.perf_counter() + delay
                step = 0.05
                while self._running and time.perf_counter() < target_time:
                    rem = max(0.0, target_time - time.perf_counter())
                    if self.on_countdown:
                        try:
                            self.on_countdown(rem)
                        except Exception:
                            pass
                    if self._stop_event.wait(min(step, rem)):
                        break
                if self.on_countdown and self._running:
                    try:
                        self.on_countdown(0.0)
                    except Exception:
                        pass
            else:
                self._wait_interruptible(delay)

    def _key_loop(self):
        """High-speed keyboard key pressing loop with jitter, limit, and slow preset countdown."""
        presses_this_session = 0
        last_counter_update = 0.0
        while self._running:
            if self._is_panic_corner():
                self._running = False
                self._stop_event.set()
                if self.on_state_change:
                    self.on_state_change(False)
                break

            if not self._do_key_press():
                break
            self.total_clicks += 1
            presses_this_session += 1

            now = time.monotonic()
            if self.on_click_callback and now - last_counter_update >= 0.05:
                try:
                    self.on_click_callback(self.total_clicks)
                    last_counter_update = now
                except Exception:
                    pass

            if self.click_limit > 0 and presses_this_session >= self.click_limit:
                self._running = False
                self._stop_event.set()
                if self.on_click_callback:
                    try:
                        self.on_click_callback(self.total_clicks)
                    except Exception:
                        pass
                if self.on_state_change:
                    self.on_state_change(False)
                break

            delay = self.get_effective_interval()
            if self.jitter_percent > 0 and not self.slow_presets:
                jitter_range = delay * self.jitter_percent
                delay += random.uniform(-jitter_range, jitter_range)
                delay = max(0.001, delay)

            if delay >= 1.0:
                target_time = time.perf_counter() + delay
                step = 0.05
                while self._running and time.perf_counter() < target_time:
                    rem = max(0.0, target_time - time.perf_counter())
                    if self.on_countdown:
                        try:
                            self.on_countdown(rem)
                        except Exception:
                            pass
                    if self._stop_event.wait(min(step, rem)):
                        break
                if self.on_countdown and self._running:
                    try:
                        self.on_countdown(0.0)
                    except Exception:
                        pass
            else:
                self._wait_interruptible(delay)
