import ctypes
from ctypes import wintypes
import time
import threading
from typing import Callable, Optional, Dict

VK_MAP: Dict[str, int] = {
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
    "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
    "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    "Mouse 4": 0x05,
    "Mouse 5": 0x06,
    "Mid Click": 0x04,
    "XButton1 (Mouse 4)": 0x05,
    "XButton2 (Mouse 5)": 0x06,
    "Middle Click": 0x04,
    "Backspace": 0x08, "Tab": 0x09, "Enter": 0x0D,
    "Shift": 0x10, "Ctrl": 0x11, "Alt": 0x12,
    "Insert": 0x2D, "Delete": 0x2E, "Home": 0x24, "End": 0x23,
    "Page Up": 0x21, "Page Down": 0x22,
    "Left": 0x25, "Up": 0x26, "Right": 0x27, "Down": 0x28,
    "Pause": 0x13, "Scroll Lock": 0x91,
    "Space": 0x20,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    "A": 0x41, "B": 0x42, "C": 0x43, "D": 0x44, "E": 0x45,
    "F": 0x46, "G": 0x47, "H": 0x48, "I": 0x49, "J": 0x4A,
    "K": 0x4B, "L": 0x4C, "M": 0x4D, "N": 0x4E, "O": 0x4F,
    "P": 0x50, "Q": 0x51, "R": 0x52, "S": 0x53, "T": 0x54,
    "U": 0x55, "V": 0x56, "W": 0x57, "X": 0x58, "Y": 0x59, "Z": 0x5A,
}


class HotkeyListener:
    """Global hotkey listener using Windows GetAsyncKeyState for zero-overhead background detection."""

    def __init__(
        self,
        key_name: str = "F6",
        on_trigger: Optional[Callable[[], None]] = None,
        on_press: Optional[Callable[[], None]] = None,
        on_release: Optional[Callable[[], None]] = None,
        trigger_mode: str = "toggle",
        vk_code: Optional[int] = None,
        on_emergency: Optional[Callable[[], None]] = None,
    ):
        self._key_name = key_name
        self._vk_code = VK_MAP.get(key_name, 0x75)  # Default F6
        if vk_code is not None:
            self._vk_code = int(vk_code)
        self.emergency_vk_code = 0x13  # Pause is a dedicated emergency stop.
        self.on_emergency = on_emergency
        self.on_trigger = on_trigger
        self.on_press = on_press
        self.on_release = on_release
        self.trigger_mode = trigger_mode  # 'toggle' or 'hold'

        self._running = False
        self._suspended = False
        self._ignore_until_release = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    @property
    def key_name(self) -> str:
        return self._key_name

    def set_key(self, key_name: str, vk_code: Optional[int] = None):
        """Update active hotkey."""
        with self._lock:
            self._key_name = key_name
            self._vk_code = int(vk_code) if vk_code is not None else VK_MAP.get(key_name, 0x75)
            self._ignore_until_release = True

    def set_trigger_mode(self, mode: str):
        """Update trigger mode ('toggle' or 'hold')."""
        with self._lock:
            self.trigger_mode = mode

    def set_suspended(self, suspended: bool):
        """Temporarily suppress the configured hotkey while binding a new key."""
        with self._lock:
            self._suspended = bool(suspended)

    def start(self):
        """Start listening for keypresses in background thread."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._listener_loop, daemon=True)
            self._thread.start()

    def stop(self):
        """Stop listening."""
        with self._lock:
            self._running = False

    def _listener_loop(self):
        was_pressed = False
        emergency_was_pressed = False
        while self._running:
            with self._lock:
                vk = self._vk_code
                suspended = self._suspended
                ignore_until_release = self._ignore_until_release
                trigger_mode = self.trigger_mode

            # Check if key is currently pressed (high bit set)
            state = ctypes.windll.user32.GetAsyncKeyState(vk)
            is_pressed = bool(state & 0x8000)

            emergency_state = ctypes.windll.user32.GetAsyncKeyState(self.emergency_vk_code)
            emergency_pressed = bool(emergency_state & 0x8000)
            if emergency_pressed and not emergency_was_pressed and self.on_emergency:
                try:
                    self.on_emergency()
                except Exception:
                    pass
            emergency_was_pressed = emergency_pressed

            if suspended:
                was_pressed = is_pressed
                time.sleep(0.015)
                continue

            if ignore_until_release:
                was_pressed = is_pressed
                if not is_pressed:
                    with self._lock:
                        self._ignore_until_release = False
                time.sleep(0.015)
                continue

            if is_pressed and not was_pressed and vk != self.emergency_vk_code:
                # Key down edge triggered
                if trigger_mode == "hold":
                    if self.on_press:
                        try:
                            self.on_press()
                        except Exception:
                            pass
                    elif self.on_trigger:
                        try:
                            self.on_trigger()
                        except Exception:
                            pass
                else:
                    if self.on_trigger:
                        try:
                            self.on_trigger()
                        except Exception:
                            pass

            elif not is_pressed and was_pressed and vk != self.emergency_vk_code:
                # Key up edge triggered
                if trigger_mode == "hold" and self.on_release:
                    try:
                        self.on_release()
                    except Exception:
                        pass

            was_pressed = is_pressed
            # 15ms poll interval gives responsive feel while using virtually 0% CPU
            time.sleep(0.015)
