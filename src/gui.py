import os
import sys
import math
import queue
import threading
import ctypes
from ctypes import wintypes
import tkinter as tk
import customtkinter as ctk
import winsound
from typing import Optional, List, Tuple, Callable
from PIL import Image, ImageDraw, ImageTk

from .engine import ClickEngine
from .hotkey import HotkeyListener, VK_MAP, VK_MID_CLICK
from .config import ConfigManager, DEFAULT_CONFIG

# Global appearance setup
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Win32 Constants for native OS window management
WM_NCLBUTTONDOWN = 0x00A1
HTCAPTION = 2
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17

# Module-level PIL image cache so gradients are computed once per process (bounded LRU)
_PIL_GRADIENT_CACHE = {}


def _cache_put_gradient(key, img, maxsize: int = 128):
    """Store in gradient cache with FIFO eviction when exceeding maxsize."""
    if len(_PIL_GRADIENT_CACHE) >= maxsize and key not in _PIL_GRADIENT_CACHE:
        try:
            oldest = next(iter(_PIL_GRADIENT_CACHE))
            del _PIL_GRADIENT_CACHE[oldest]
        except Exception:
            pass
    _PIL_GRADIENT_CACHE[key] = img


def _lerp_color(c1: Tuple[int, int, int], c2: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _sample_stops(stops: List[Tuple[float, Tuple[int, int, int]]], t: float) -> Tuple[int, int, int]:
    if t <= stops[0][0]:
        return stops[0][1]
    if t >= stops[-1][0]:
        return stops[-1][1]
    for i in range(len(stops) - 1):
        p0, c0 = stops[i]
        p1, c1 = stops[i + 1]
        if p0 <= t <= p1:
            local_t = (t - p0) / max(1e-6, p1 - p0)
            return _lerp_color(c0, c1, local_t)
    return stops[-1][1]


def _bake_rect_gradient_pil(
    width: int,
    height: int,
    stops: Tuple[Tuple[float, Tuple[int, int, int]], ...],
    border_color: Optional[Tuple[int, int, int]] = None,
    top_shine: Optional[Tuple[int, int, int]] = None,
    bottom_bevel: Optional[Tuple[int, int, int]] = None,
    bg_corner: Optional[Tuple[int, int, int]] = None,
) -> Image.Image:
    width = max(2, int(width))
    height = max(2, int(height))
    key = ("rect", width, height, stops, border_color, top_shine, bottom_bevel, bg_corner)
    if key in _PIL_GRADIENT_CACHE:
        return _PIL_GRADIENT_CACHE[key]

    img = Image.new("RGB", (width, height))
    pixels = []
    stops_list = list(stops)
    h_f = float(max(1, height - 1))

    for y in range(height):
        yf = y / h_f
        row_col = _sample_stops(stops_list, yf)
        for x in range(width):
            col = row_col
            is_edge = (x == 0 or x == width - 1 or y == 0 or y == height - 1)
            is_corner = (x in (0, width - 1)) and (y in (0, height - 1))

            if is_corner and bg_corner is not None and border_color is not None:
                col = _lerp_color(border_color, bg_corner, 0.35)
            elif bottom_bevel is not None and y == height - 1 and 0 < x < width - 1:
                col = bottom_bevel
            elif is_edge and border_color is not None:
                col = border_color
            elif top_shine is not None and y == 1 and 0 < x < width - 1:
                col = top_shine

            pixels.append(col)

    img.putdata(pixels)
    _cache_put_gradient(key, img)
    return img


def _bake_action_circle_badge_pil(size: int, mode: str, hover: bool) -> Image.Image:
    """Bake 4x supersampled anti-aliased circular glossy action badge (emerald play / amber stop)."""
    key = ("badge", size, mode, hover)
    if key in _PIL_GRADIENT_CACHE:
        return _PIL_GRADIENT_CACHE[key]

    scale = 4
    ss = size * scale
    bg_rgb = (243, 246, 250)  # Matches tray midpoint background
    img = Image.new("RGB", (ss, ss), bg_rgb)
    pixels = []

    cx = (ss - 1) * 0.5
    cy = (ss - 1) * 0.5
    radius = (ss * 0.5) - 2.0

    # Light source at top-left (35%, 28%)
    lx = ss * 0.35
    ly = ss * 0.26
    max_d = radius * 1.85

    if mode == "start":
        if hover:
            stops = [
                (0.0, (236, 253, 245)),
                (0.28, (52, 211, 153)),
                (0.68, (16, 185, 129)),
                (1.0, (4, 120, 87)),
            ]
        else:
            stops = [
                (0.0, (209, 250, 229)),
                (0.30, (52, 211, 153)),
                (0.70, (5, 150, 105)),
                (1.0, (6, 78, 59)),
            ]
        ring_col = (4, 120, 87)
    else:
        if hover:
            stops = [
                (0.0, (255, 251, 225)),
                (0.28, (251, 191, 36)),
                (0.68, (234, 88, 12)),
                (1.0, (154, 52, 18)),
            ]
        else:
            stops = [
                (0.0, (254, 243, 176)),
                (0.32, (246, 173, 85)),
                (0.72, (221, 107, 32)),
                (1.0, (156, 66, 33)),
            ]
        ring_col = (180, 83, 9)

    for y in range(ss):
        for x in range(ss):
            dx = x - cx
            dy = y - cy
            dist = math.sqrt(dx * dx + dy * dy)

            if dist > radius + 1.0:
                pixels.append(bg_rgb)
            else:
                ldx = x - lx
                ldy = y - ly
                ldist = math.sqrt(ldx * ldx + ldy * ldy) / max_d
                base_col = _sample_stops(stops, ldist)

                yf = (y - (cy - radius)) / max(1.0, radius * 2.0)
                if yf < 0.46:
                    sheen = (0.46 - yf) * 0.42
                    base_col = _lerp_color(base_col, (255, 255, 255), sheen)

                if dist > radius - 3.2:
                    edge_t = min(1.0, (dist - (radius - 3.2)) / 3.2)
                    base_col = _lerp_color(base_col, ring_col, edge_t * 0.85)
                elif dist > radius - 6.0 and yf < 0.5:
                    base_col = _lerp_color(base_col, (255, 255, 255), 0.35)

                if dist > radius - 0.5:
                    aa = max(0.0, min(1.0, (radius + 0.8 - dist) / 1.3))
                    base_col = _lerp_color(bg_rgb, base_col, aa)

                pixels.append(base_col)

    img.putdata(pixels)
    draw = ImageDraw.Draw(img)

    if mode == "start":
        p1 = (int(ss * 0.39), int(ss * 0.30))
        p2 = (int(ss * 0.39), int(ss * 0.70))
        p3 = (int(ss * 0.71), int(ss * 0.50))
        draw.polygon([(p1[0], p1[1] + 2), (p2[0], p2[1] + 2), (p3[0], p3[1] + 2)], fill=(4, 78, 56))
        draw.polygon([p1, p2, p3], fill=(255, 255, 255))
    else:
        s0 = int(ss * 0.34)
        s1 = int(ss * 0.66)
        draw.rectangle([s0, s0 + 2, s1, s1 + 2], fill=(140, 55, 18))
        draw.rectangle([s0, s0, s1, s1], fill=(255, 255, 255))

    final_img = img.resize((size, size), Image.Resampling.LANCZOS)
    _cache_put_gradient(key, final_img)
    return final_img


class _MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


# Private user32 handle so argtypes/restype (64-bit HMONITOR) don't leak into ctypes.windll.user32
_user32_typed = ctypes.WinDLL("user32")
_user32_typed.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
_user32_typed.MonitorFromPoint.restype = wintypes.HMONITOR
_user32_typed.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MonitorInfo)]
_user32_typed.GetMonitorInfoW.restype = wintypes.BOOL


def _nearest_monitor_work_area(x: int, y: int) -> Optional[Tuple[int, int, int, int]]:
    """Return (left, top, right, bottom) of the work area on the monitor nearest to (x, y)."""
    try:
        hmon = _user32_typed.MonitorFromPoint(wintypes.POINT(int(x), int(y)), 2)  # MONITOR_DEFAULTTONEAREST
        if not hmon:
            return None
        info = _MonitorInfo()
        info.cbSize = ctypes.sizeof(_MonitorInfo)
        if not _user32_typed.GetMonitorInfoW(hmon, ctypes.byref(info)):
            return None
        rc = info.rcWork
        return rc.left, rc.top, rc.right, rc.bottom
    except Exception:
        return None


def _format_elapsed_mmss(seconds: float) -> str:
    total = max(0, int(seconds))
    hrs = total // 3600
    mins = (total % 3600) // 60
    secs = total % 60
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


class ToolTip:
    """Lightweight, sleek floating tooltip for CustomTkinter and Canvas widgets."""

    def __init__(self, widget, text: str, delay_ms: int = 350):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.tip_window: Optional[ctk.CTkToplevel] = None
        self._after_id = None

        self._bind_events(self.widget)
        for child in self.widget.winfo_children():
            self._bind_events(child)

        try:
            self.widget.bind("<Destroy>", lambda e: self.hide(), add="+")
        except Exception:
            pass

    def _bind_events(self, w):
        try:
            w.bind("<Enter>", self._on_enter, add="+")
            w.bind("<Leave>", self._on_leave, add="+")
            w.bind("<ButtonPress>", self._on_leave, add="+")
        except Exception:
            pass

    def _on_enter(self, event=None):
        self._cancel_timer()
        try:
            self._after_id = self.widget.after(self.delay_ms, self._show_tip)
        except Exception:
            pass

    def _on_leave(self, event=None):
        self._cancel_timer()
        self.hide()

    def _cancel_timer(self):
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show_tip(self):
        if self.tip_window or not self.text:
            return

        try:
            if not self.widget.winfo_exists():
                return
            x = self.widget.winfo_rootx() + 4
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4

            self.tip_window = tw = ctk.CTkToplevel(self.widget)
            tw.overrideredirect(True)
            tw.attributes("-topmost", True)
            tw.configure(fg_color="#1e2227")

            frame = ctk.CTkFrame(
                tw,
                fg_color="#1e2227",
                border_width=1,
                border_color="#4b5263",
                corner_radius=2
            )
            frame.pack(fill="both", expand=True)

            lbl = ctk.CTkLabel(
                frame,
                text=self.text,
                font=ctk.CTkFont(family="Segoe UI", size=9),
                text_color="#e2e8f0",
                padx=8,
                pady=3
            )
            lbl.pack()

            tw.update_idletasks()
            w = tw.winfo_reqwidth()
            h = tw.winfo_reqheight()

            screen_w = tw.winfo_screenwidth()
            screen_h = tw.winfo_screenheight()
            if x + w > screen_w - 10:
                x = screen_w - w - 10
            if y + h > screen_h - 10:
                y = self.widget.winfo_rooty() - h - 4

            tw.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            self.hide()

    def hide(self):
        self._cancel_timer()
        if self.tip_window:
            try:
                self.tip_window.destroy()
            except Exception:
                pass
            self.tip_window = None


class AeroSegmentedButton(ctk.CTkFrame):
    """Recessed gradient well with metallic steel-graphite active segment & sharp 1px corners."""

    WELL_STOPS = (
        (0.0, (216, 224, 235)),
        (0.3, (228, 234, 243)),
        (1.0, (240, 244, 249)),
    )
    ACTIVE_STOPS = (
        (0.0, (78, 93, 115)),
        (0.48, (54, 67, 84)),
        (0.52, (40, 51, 66)),
        (1.0, (30, 41, 59)),
    )
    HOVER_STOPS = (
        (0.0, (255, 255, 255)),
        (1.0, (233, 239, 247)),
    )

    def __init__(
        self,
        master,
        values: List[str],
        command: Optional[Callable[[str], None]] = None,
        height: int = 21,
        font_size: int = 8,
        pad_x: int = 9,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self._values = list(values)
        self._command = command
        self._height = height
        self._font_size = font_size
        self._current_value = self._values[0] if self._values else ""
        self._hover_index: Optional[int] = None

        self._seg_widths = []
        for v in self._values:
            clean_v = v.replace("🎣 ", "")
            w = max(28, len(clean_v) * 6 + pad_x * 2)
            self._seg_widths.append(w)

        self._total_w = sum(self._seg_widths) + 2
        self._photos = {}

        self.canvas = tk.Canvas(
            self,
            width=self._total_w,
            height=self._height,
            bg="#f4f6f9",
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.canvas.pack(fill="both", expand=True)

        self._bake_textures()
        self._redraw()

        self.canvas.bind("<ButtonPress-1>", self._on_click)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)

    def _bake_textures(self):
        well_pil = _bake_rect_gradient_pil(
            self._total_w,
            self._height,
            self.WELL_STOPS,
            border_color=(176, 190, 209),
            top_shine=(202, 212, 226),
            bg_corner=(244, 246, 249),
        )
        self._photos["well"] = ImageTk.PhotoImage(well_pil, master=self)

        for idx, sw in enumerate(self._seg_widths):
            act_pil = _bake_rect_gradient_pil(
                sw,
                self._height - 2,
                self.ACTIVE_STOPS,
                border_color=(23, 32, 46),
                top_shine=(108, 125, 150),
            )
            hov_pil = _bake_rect_gradient_pil(
                sw,
                self._height - 2,
                self.HOVER_STOPS,
                border_color=(181, 194, 211),
                top_shine=(255, 255, 255),
            )
            self._photos[("act", idx)] = ImageTk.PhotoImage(act_pil, master=self)
            self._photos[("hov", idx)] = ImageTk.PhotoImage(hov_pil, master=self)

    def _redraw(self):
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self._photos["well"], anchor="nw")

        x_cursor = 1
        for idx, val in enumerate(self._values):
            sw = self._seg_widths[idx]
            is_sel = (val == self._current_value) or (
                val.replace("🎣 ", "") == str(self._current_value).replace("🎣 ", "")
            )
            is_hov = (self._hover_index == idx)

            if is_sel:
                self.canvas.create_image(x_cursor, 1, image=self._photos[("act", idx)], anchor="nw")
                txt_col = "#ffffff"
                fnt = ("Segoe UI", self._font_size, "bold")
            elif is_hov:
                self.canvas.create_image(x_cursor, 1, image=self._photos[("hov", idx)], anchor="nw")
                txt_col = "#0f172a"
                fnt = ("Segoe UI", self._font_size, "bold")
            else:
                txt_col = "#475569"
                fnt = ("Segoe UI", self._font_size, "bold")
                if idx > 0:
                    prev_val = self._values[idx - 1]
                    prev_sel = (prev_val == self._current_value)
                    if not prev_sel:
                        self.canvas.create_line(
                            x_cursor, 3, x_cursor, self._height - 3, fill="#c4d0df"
                        )

            display_label = val.replace("🎣 ", "")
            self.canvas.create_text(
                x_cursor + sw // 2,
                self._height // 2,
                text=display_label,
                font=fnt,
                fill=txt_col,
            )
            x_cursor += sw

    def _index_at(self, x: int) -> Optional[int]:
        cur = 1
        for idx, sw in enumerate(self._seg_widths):
            if cur <= x < cur + sw:
                return idx
            cur += sw
        return None

    def _on_click(self, event):
        idx = self._index_at(event.x)
        if idx is not None:
            chosen = self._values[idx]
            if chosen != self._current_value:
                self._current_value = chosen
                self._redraw()
                if self._command:
                    self._command(chosen)

    def _on_motion(self, event):
        idx = self._index_at(event.x)
        if idx != self._hover_index:
            self._hover_index = idx
            self._redraw()

    def _on_leave(self, event):
        if self._hover_index is not None:
            self._hover_index = None
            self._redraw()

    def set(self, value: str):
        if value in self._values:
            self._current_value = value
        else:
            clean = str(value).replace("🎣 ", "")
            for v in self._values:
                if v.replace("🎣 ", "") == clean:
                    self._current_value = v
                    break
        self._redraw()

    def get(self) -> str:
        return self._current_value


class AeroKeycapButton(ctk.CTkFrame):
    """Tactile beveled keycap/action button with pre-baked PIL gradient & sharp 1px corners."""

    KEYCAP_NORM = (
        (0.0, (255, 255, 255)),
        (0.55, (246, 248, 252)),
        (1.0, (233, 238, 246)),
    )
    KEYCAP_HOVER = (
        (0.0, (255, 255, 255)),
        (1.0, (242, 246, 252)),
    )
    STEEL_NORM = (
        (0.0, (78, 93, 115)),
        (0.5, (51, 65, 85)),
        (1.0, (30, 41, 59)),
    )
    STEEL_HOVER = (
        (0.0, (92, 108, 132)),
        (0.5, (62, 78, 100)),
        (1.0, (38, 52, 72)),
    )
    DANGER_NORM = (
        (0.0, (255, 245, 245)),
        (1.0, (254, 226, 226)),
    )
    DANGER_HOVER = (
        (0.0, (254, 226, 226)),
        (1.0, (252, 198, 198)),
    )

    def __init__(
        self,
        master,
        text: str = "",
        width: int = 80,
        height: int = 21,
        style: str = "keycap",
        font_size: int = 8,
        command: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", width=width, height=height, corner_radius=0)
        self._text = text
        self._width = width
        self._height = height
        self._style = style  # "keycap", "steel", "danger"
        self._font_size = font_size
        self._command = command
        self._hover = False
        self._photos = {}

        self.canvas = tk.Canvas(
            self,
            width=self._width,
            height=self._height,
            bg="#f4f6f9",
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.canvas.pack(fill="both", expand=True)

        self._bake()
        self._redraw()

        self.canvas.bind("<ButtonPress-1>", self._on_click)
        self.canvas.bind("<Enter>", self._on_enter)
        self.canvas.bind("<Leave>", self._on_leave)

    def _bake(self):
        for st, norm_stops, hov_stops, b_norm, b_hov, shine, bev in [
            (
                "keycap",
                self.KEYCAP_NORM,
                self.KEYCAP_HOVER,
                (176, 190, 209),
                (115, 132, 156),
                (255, 255, 255),
                (124, 139, 161),
            ),
            (
                "steel",
                self.STEEL_NORM,
                self.STEEL_HOVER,
                (23, 32, 46),
                (15, 23, 42),
                (108, 125, 150),
                (15, 23, 42),
            ),
            (
                "danger",
                self.DANGER_NORM,
                self.DANGER_HOVER,
                (248, 165, 165),
                (239, 108, 108),
                (255, 255, 255),
                (220, 120, 120),
            ),
        ]:
            p_n = _bake_rect_gradient_pil(
                self._width,
                self._height,
                norm_stops,
                border_color=b_norm,
                top_shine=shine,
                bottom_bevel=bev,
                bg_corner=(244, 246, 249),
            )
            p_h = _bake_rect_gradient_pil(
                self._width,
                self._height,
                hov_stops,
                border_color=b_hov,
                top_shine=shine,
                bottom_bevel=bev,
                bg_corner=(244, 246, 249),
            )
            self._photos[(st, False)] = ImageTk.PhotoImage(p_n, master=self)
            self._photos[(st, True)] = ImageTk.PhotoImage(p_h, master=self)

    _SHORT_KEY_LABELS = {
        "Backspace": "Bksp",
        "BackSpace": "Bksp",
        "Page Up": "PgUp",
        "Page Down": "PgDn",
        "Scroll Lock": "ScrLk",
        "Caps Lock": "CapsLk",
        "Num Lock": "NumLk",
        "Mid Click": "MidClk",
        "Middle Click": "MidClk",
        "XButton1 (Mouse 4)": "Mouse 4",
        "XButton2 (Mouse 5)": "Mouse 5",
    }

    def _redraw(self):
        self.canvas.delete("all")
        img = self._photos.get((self._style, self._hover)) or self._photos[("keycap", False)]
        self.canvas.create_image(0, 0, image=img, anchor="nw")

        if self._style == "keycap" and ("• Bind" in self._text or " Bind" in self._text):
            raw_key = self._text.replace("• Bind", "").replace("Bind", "").strip()
            key_part = self._SHORT_KEY_LABELS.get(raw_key, raw_key)
            if len(key_part) > 7:
                key_part = key_part[:7]
            cy = (self._height - 1) // 2
            if len(key_part) <= 3:
                cx = self._width // 2
                self.canvas.create_text(
                    cx - 12,
                    cy,
                    text=key_part,
                    font=("Segoe UI", self._font_size, "bold"),
                    fill="#0f172a",
                )
                self.canvas.create_text(
                    cx + 15,
                    cy,
                    text="Bind",
                    font=("Segoe UI", self._font_size),
                    fill="#64748b",
                )
            else:
                # Longer key names like "Mouse 4" or "Mouse 5"
                self.canvas.create_text(
                    7,
                    cy,
                    text=key_part,
                    font=("Segoe UI", self._font_size, "bold"),
                    fill="#0f172a",
                    anchor="w",
                )
                self.canvas.create_text(
                    self._width - 6,
                    cy,
                    text="Bind",
                    font=("Segoe UI", max(7, self._font_size - 1)),
                    fill="#64748b",
                    anchor="e",
                )
        else:
            if self._style == "steel":
                txt_col = "#ffffff"
            elif self._style == "danger":
                txt_col = "#b91c1c"
            else:
                txt_col = "#1e293b"
            disp_text = self._text
            if "• Key" in disp_text:
                raw_k = disp_text.replace("• Key", "").strip()
                short_k = self._SHORT_KEY_LABELS.get(raw_k, raw_k)
                if len(short_k) > 7:
                    short_k = short_k[:7]
                disp_text = f"{short_k} • Key"
            self.canvas.create_text(
                self._width // 2,
                (self._height - 1) // 2,
                text=disp_text,
                font=("Segoe UI", self._font_size, "bold"),
                fill=txt_col,
            )

    def _on_click(self, event):
        if self._command:
            self._command()

    def _on_enter(self, event):
        self._hover = True
        self._redraw()

    def _on_leave(self, event):
        self._hover = False
        self._redraw()

    def configure(self, **kwargs):
        if "text" in kwargs:
            self._text = kwargs.pop("text")
        if "fg_color" in kwargs:
            fg = kwargs.pop("fg_color")
            if fg in ("#0284c7", "#2563eb", "#334155", "#1e293b"):
                self._style = "steel"
            elif fg == "#fee2e2":
                self._style = "danger"
            else:
                self._style = "keycap"
        for k in ("hover_color", "text_color", "border_width", "border_color", "corner_radius"):
            kwargs.pop(k, None)
        if kwargs:
            super().configure(**kwargs)
        self._redraw()

    def cget(self, key: str):
        if key == "text":
            return self._text
        return super().cget(key)


class AeroCheckBox(ctk.CTkFrame):
    """Sharp 1px technical checkbox with recessed well & metallic steel checked gradient."""

    BOX_UNCHECKED = (
        (0.0, (214, 222, 234)),
        (0.4, (238, 242, 248)),
        (1.0, (255, 255, 255)),
    )
    BOX_CHECKED = (
        (0.0, (78, 93, 115)),
        (0.5, (51, 65, 85)),
        (1.0, (30, 41, 59)),
    )

    def __init__(
        self,
        master,
        text: str = "",
        command: Optional[Callable[[], None]] = None,
        font_size: int = 8,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self._text = text
        self._command = command
        self._checked = False
        self._hover = False
        self._box_size = 13

        un_pil = _bake_rect_gradient_pil(
            self._box_size,
            self._box_size,
            self.BOX_UNCHECKED,
            border_color=(148, 163, 184),
            top_shine=(203, 213, 225),
        )
        un_hov_pil = _bake_rect_gradient_pil(
            self._box_size,
            self._box_size,
            self.BOX_UNCHECKED,
            border_color=(71, 85, 105),
            top_shine=(226, 232, 240),
        )
        chk_pil = _bake_rect_gradient_pil(
            self._box_size,
            self._box_size,
            self.BOX_CHECKED,
            border_color=(15, 23, 42),
            top_shine=(108, 125, 150),
        ).copy()

        draw = ImageDraw.Draw(chk_pil)
        draw.line([(3, 6), (5, 9), (10, 3)], fill=(255, 255, 255), width=2)

        self._photos = {
            (False, False): ImageTk.PhotoImage(un_pil, master=self),
            (False, True): ImageTk.PhotoImage(un_hov_pil, master=self),
            (True, False): ImageTk.PhotoImage(chk_pil, master=self),
            (True, True): ImageTk.PhotoImage(chk_pil, master=self),
        }

        self.box_canvas = tk.Canvas(
            self,
            width=self._box_size,
            height=self._box_size,
            bg="#f4f6f9",
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.box_canvas.pack(side="left", pady=1)

        self.lbl = ctk.CTkLabel(
            self,
            text=self._text,
            font=ctk.CTkFont(family="Segoe UI", size=font_size + 1),
            text_color="#334155",
            cursor="hand2",
        )
        self.lbl.pack(side="left", padx=(5, 0))

        self._redraw()

        for w in (self, self.box_canvas, self.lbl):
            w.bind("<ButtonPress-1>", self._on_toggle)
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)

    def _redraw(self):
        self.box_canvas.delete("all")
        self.box_canvas.create_image(
            0, 0, image=self._photos[(self._checked, self._hover)], anchor="nw"
        )
        self.lbl.configure(text_color="#0f172a" if self._hover else "#334155")

    def _on_toggle(self, event=None):
        self._checked = not self._checked
        self._redraw()
        if self._command:
            self._command()

    def _on_enter(self, event=None):
        self._hover = True
        self._redraw()

    def _on_leave(self, event=None):
        self._hover = False
        self._redraw()

    def select(self):
        self._checked = True
        self._redraw()

    def deselect(self):
        self._checked = False
        self._redraw()

    def get(self) -> int:
        return 1 if self._checked else 0


class AeroSlider(ctk.CTkFrame):
    """Recessed gradient track slider with metallic steel progress fill and beveled rectangular thumb."""

    TRACK_STOPS = (
        (0.0, (196, 206, 220)),
        (0.5, (216, 224, 235)),
        (1.0, (235, 240, 247)),
    )
    FILL_STOPS = (
        (0.0, (78, 93, 115)),
        (0.5, (51, 65, 85)),
        (1.0, (30, 41, 59)),
    )
    THUMB_NORM = (
        (0.0, (255, 255, 255)),
        (0.5, (238, 242, 247)),
        (1.0, (203, 213, 225)),
    )
    THUMB_HOVER = (
        (0.0, (255, 255, 255)),
        (0.5, (245, 248, 252)),
        (1.0, (218, 226, 236)),
    )

    def __init__(
        self,
        master,
        from_: float = 1.0,
        to: float = 1000.0,
        command: Optional[Callable[[float], None]] = None,
        height: int = 16,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", height=height, corner_radius=0)
        self._from = float(from_)
        self._to = float(to)
        self._val = self._from
        self._command = command
        self._height = height
        self._hover = False
        self._thumb_w = 11
        self._thumb_h = 14
        self._track_h = 6
        self._photos = {}

        self.canvas = tk.Canvas(
            self,
            height=self._height,
            bg="#f4f6f9",
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.canvas.pack(fill="x", expand=True)

        t_norm = _bake_rect_gradient_pil(
            self._thumb_w,
            self._thumb_h,
            self.THUMB_NORM,
            border_color=(100, 116, 139),
            top_shine=(255, 255, 255),
            bottom_bevel=(71, 85, 105),
        )
        t_hov = _bake_rect_gradient_pil(
            self._thumb_w,
            self._thumb_h,
            self.THUMB_HOVER,
            border_color=(51, 65, 85),
            top_shine=(255, 255, 255),
            bottom_bevel=(30, 41, 59),
        )
        self._photos["thumb_norm"] = ImageTk.PhotoImage(t_norm, master=self)
        self._photos["thumb_hov"] = ImageTk.PhotoImage(t_hov, master=self)

        self.canvas.bind("<Configure>", lambda e: self._redraw())
        self.canvas.bind("<ButtonPress-1>", self._on_press_or_drag)
        self.canvas.bind("<B1-Motion>", self._on_press_or_drag)
        self.canvas.bind("<Enter>", self._on_enter)
        self.canvas.bind("<Leave>", self._on_leave)

    def _redraw(self):
        w = self.canvas.winfo_width()
        if w < 30:
            w = 300
        self.canvas.delete("all")

        pad = self._thumb_w // 2 + 1
        usable_w = max(10, w - pad * 2)
        cy = self._height // 2
        ty = cy - self._track_h // 2

        track_pil = _bake_rect_gradient_pil(
            usable_w,
            self._track_h,
            self.TRACK_STOPS,
            border_color=(165, 179, 198),
        )
        self._photos["track"] = ImageTk.PhotoImage(track_pil, master=self)
        self.canvas.create_image(pad, ty, image=self._photos["track"], anchor="nw")

        span = max(1e-6, self._to - self._from)
        ratio = max(0.0, min(1.0, (self._val - self._from) / span))
        fill_w = int(usable_w * ratio)

        if fill_w >= 3:
            fill_pil = _bake_rect_gradient_pil(
                fill_w,
                self._track_h,
                self.FILL_STOPS,
                border_color=(30, 41, 59),
            )
            self._photos["fill"] = ImageTk.PhotoImage(fill_pil, master=self)
            self.canvas.create_image(pad, ty, image=self._photos["fill"], anchor="nw")

        thumb_x = pad + fill_w - (self._thumb_w // 2)
        thumb_y = cy - (self._thumb_h // 2)
        t_img = self._photos["thumb_hov"] if self._hover else self._photos["thumb_norm"]
        self.canvas.create_image(thumb_x, thumb_y, image=t_img, anchor="nw")

    def _on_press_or_drag(self, event):
        w = self.canvas.winfo_width()
        if w < 30:
            return
        pad = self._thumb_w // 2 + 1
        usable_w = max(10, w - pad * 2)
        ratio = max(0.0, min(1.0, (event.x - pad) / float(usable_w)))
        new_val = self._from + ratio * (self._to - self._from)
        self._val = new_val
        self._redraw()
        if self._command:
            self._command(self._val)

    def _on_enter(self, event):
        self._hover = True
        self._redraw()

    def _on_leave(self, event):
        self._hover = False
        self._redraw()

    def set(self, val: float):
        self._val = max(self._from, min(self._to, float(val)))
        self._redraw()

    def get(self) -> float:
        return self._val

    def configure(self, **kwargs):
        if "from_" in kwargs:
            self._from = float(kwargs.pop("from_"))
        if "to" in kwargs:
            self._to = float(kwargs.pop("to"))
        if kwargs:
            super().configure(**kwargs)
        self._val = max(self._from, min(self._to, self._val))
        self._redraw()


class _ToggleBtnProxy:
    """Compatibility proxy for self.toggle_btn so external/legacy calls update the action tray."""

    def __init__(self, app: "AutoclickerApp"):
        self._app = app
        self._text = "START (F6)"

    def configure(self, **kwargs):
        if "text" in kwargs:
            self._text = kwargs["text"]
            self._app._redraw_action_tray()

    def cget(self, key: str):
        if key == "text":
            return self._text
        return ""


class AutoclickerApp(ctk.CTk):
    """Native Win32-accelerated frameless Aero GUI: zero resize lag, zero minimize freeze."""

    NORMAL_WIDTH = 345
    MINI_WIDTH = 315
    DEFAULT_VERTICAL_BREATHING_ROOM = 10
    RESIZE_BORDER = 7

    TRAY_NORM_STOPS = (
        (0.0, (251, 252, 254)),
        (1.0, (235, 240, 247)),
    )
    TRAY_HOVER_STOPS = (
        (0.0, (255, 255, 255)),
        (1.0, (241, 245, 251)),
    )

    def __init__(self):
        super().__init__()

        self.title("LTC Auto Clicker")
        self.geometry("345x315")
        self.minsize(self.MINI_WIDTH, 185)
        self.resizable(True, True)
        self.configure(fg_color="#232830")
        self.overrideredirect(True)

        # Resolve asset base directory
        if getattr(sys, "frozen", False):
            base_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        else:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        self._icon_path = os.path.join(base_dir, "assets", "icon.ico")
        if os.path.exists(self._icon_path):
            try:
                self.iconbitmap(self._icon_path)
            except Exception:
                pass

        # Configuration Manager
        self.config_manager = ConfigManager()
        self.cfg = self.config_manager.load()

        # Thread-safe event queue for cross-thread engine notifications
        self._event_queue = queue.Queue()
        self._queue_poll_after_id = None

        # Core Engine and Hotkey Listener
        self.engine = ClickEngine()
        self.engine.on_click_callback = lambda count: self._event_queue.put(("click", count))
        self.engine.on_state_change = lambda is_running: self._event_queue.put(("state", is_running))
        self.engine.on_countdown = lambda rem: self._event_queue.put(("countdown", rem))
        self.engine.on_error = lambda err: self._event_queue.put(("error", err))
        self._poll_event_queue()

        # Load initial engine parameters
        self.active_mode = self.cfg.get("active_mode", "clicker")
        self.current_unit = self.cfg.get("speed_unit", "ms")
        self.engine.mode = self.active_mode
        self.engine.button = self.cfg.get("mouse_button", "left")
        self.engine.click_type = self.cfg.get("click_type", "single")
        t_key = str(self.cfg.get("target_key", "Space"))
        self.engine.target_key = t_key
        self.engine.target_key_vk = int(self.cfg.get("target_key_vk", VK_MAP.get(t_key, 0x20)))
        self.engine.jitter_percent = 0.10 if self.cfg.get("jitter", False) else 0.0
        self.engine.click_limit = self.cfg.get("click_limit", 0)
        self.engine.hold_duration_sec = self.cfg.get("hold_duration_ms", 15) / 1000.0
        self.engine.panic_corner = self.cfg.get("panic_corner", True)
        self.engine.self_click_protection = self.cfg.get("self_click_protection", True)
        self.engine.lock_cursor_pos = self.cfg.get("lock_cursor_pos", False)
        lx = int(self.cfg.get("locked_x", -1))
        ly = int(self.cfg.get("locked_y", -1))
        self.engine.locked_pos = (lx, ly) if (lx >= 0 and ly >= 0) else None
        self.engine.central_scatter = self.cfg.get("central_scatter", False)
        self.engine.slow_presets = self.cfg.get("slow_presets", False)
        self.engine.slow_preset_choice = self.cfg.get("slow_preset_choice", "fast")

        hotkey_name = self.cfg.get("hotkey", "F6")
        self.hotkey_vk_code = int(self.cfg.get("hotkey_vk", VK_MAP.get(hotkey_name, 0x75)))
        trigger_mode = self.cfg.get("trigger_mode", "toggle")
        self.hotkey_listener = HotkeyListener(
            key_name=hotkey_name,
            on_trigger=self._on_hotkey_trigger,
            on_press=self._on_hotkey_press,
            on_release=self._on_hotkey_release,
            trigger_mode=trigger_mode,
            vk_code=self.hotkey_vk_code,
            on_emergency=self._on_emergency_stop
        )
        self.hotkey_listener.start()

        # State tracking
        self.sound_enabled = bool(self.cfg.get("sound_enabled", True))
        self.is_compact_mode = False
        self.is_settings_open = False
        self._capturing_hotkey = False
        self._hotkey_capture_binding = None
        self._mouse_capture_after_id = None
        self._capturing_target_key = False
        self._target_key_capture_binding = None
        self._picking_pos = False
        self._pick_pos_after_id = None
        self._session_timer_after_id = None
        self._state_after_id = None
        self._click_after_id = None
        self._countdown_after_id = None
        self._save_after_id = None
        self._tex_after_id = None
        self._taskbar_after_id = None
        self._taskbar_retry_after_id = None
        self._fit_after_id = None
        self._input_error = False
        self._hwnd: Optional[int] = None
        self._is_minimized = False
        self._saved_geo = None
        self._window_pos: Optional[Tuple[int, int]] = None
        self._tray_hover = False
        self._tray_photos = {}

        # Pre-bake master PIL textures ONCE at startup
        self._master_body_img = self._bake_master_body_image(96, 80)
        self._btn_imgs = {
            "min_norm": self._bake_aero_button(27, 17, is_close=False, hover=False),
            "min_hover": self._bake_aero_button(27, 17, is_close=False, hover=True),
            "close_norm": self._bake_aero_button(38, 17, is_close=True, hover=False),
            "close_hover": self._bake_aero_button(38, 17, is_close=True, hover=True),
            "badge_start_norm": ImageTk.PhotoImage(_bake_action_circle_badge_pil(28, "start", False), master=self),
            "badge_start_hover": ImageTk.PhotoImage(_bake_action_circle_badge_pil(28, "start", True), master=self),
            "badge_stop_norm": ImageTk.PhotoImage(_bake_action_circle_badge_pil(28, "stop", False), master=self),
            "badge_stop_hover": ImageTk.PhotoImage(_bake_action_circle_badge_pil(28, "stop", True), master=self),
        }
        self._active_bg_photo: Optional[ImageTk.PhotoImage] = None
        self._last_drawn_size = (0, 0)

        self._build_ui()
        self._apply_initial_ui_state(self.cfg)
        self.bind("<Map>", self._on_window_map)
        self._taskbar_after_id = self.after(20, self._enable_taskbar_icon)
        self._taskbar_retry_after_id = self.after(250, self._enable_taskbar_icon)
        self._schedule_fit_window()

        # Bring window into view and focus upon startup
        try:
            self.lift()
            self.focus_force()
            hwnd = self._get_hwnd()
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def _schedule_fit_window(self):
        if self._fit_after_id:
            try:
                self.after_cancel(self._fit_after_id)
            except Exception:
                pass
        try:
            self._fit_after_id = self.after_idle(self._fit_window_to_content)
        except Exception:
            pass

    def _get_hwnd(self) -> int:
        return ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()

    def _enable_taskbar_icon(self):
        """Force the borderless overrideredirect window to appear on the Windows taskbar & register HWND."""
        self._taskbar_after_id = None
        if self._is_minimized or not self.winfo_exists():
            return
        try:
            user32 = ctypes.windll.user32
            hwnd = self._get_hwnd()
            self.engine.protected_hwnd = hwnd
            GWL_STYLE = -16
            GWL_EXSTYLE = -20
            WS_SYSMENU = 0x00080000
            WS_MINIMIZEBOX = 0x00020000
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080

            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            new_style = style | WS_SYSMENU | WS_MINIMIZEBOX
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            new_ex_style = (ex_style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW

            needs_re_show = (ex_style & WS_EX_APPWINDOW) == 0 or (ex_style & WS_EX_TOOLWINDOW) != 0
            if needs_re_show:
                user32.ShowWindow(hwnd, 0)  # SW_HIDE so Windows Shell registers the taskbar button on SW_SHOW
            user32.SetWindowLongW(hwnd, GWL_STYLE, ctypes.c_int(new_style).value)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ctypes.c_int(new_ex_style).value)

            if hasattr(self, "_icon_path") and os.path.exists(self._icon_path):
                IMAGE_ICON = 1
                LR_LOADFROMFILE = 0x0010
                LR_SHARED = 0x8000
                WM_SETICON = 0x0080
                flags = LR_LOADFROMFILE | LR_SHARED
                hicon_sm = user32.LoadImageW(None, self._icon_path, IMAGE_ICON, 16, 16, flags)
                hicon_lg = user32.LoadImageW(None, self._icon_path, IMAGE_ICON, 32, 32, flags)
                if hicon_sm:
                    user32.SendMessageW(hwnd, WM_SETICON, 0, hicon_sm)
                if hicon_lg:
                    user32.SendMessageW(hwnd, WM_SETICON, 1, hicon_lg)

            SWP_FRAMECHANGED = 0x0020
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER)
            if needs_re_show:
                user32.ShowWindow(hwnd, 5)  # SW_SHOW
        except Exception:
            pass

    # =========================================================================
    # Pre-Baked C-Accelerated PIL Textures
    # =========================================================================

    def _bake_aero_button(self, width: int, height: int, is_close: bool, hover: bool) -> ImageTk.PhotoImage:
        key = ("aero_caption", width, height, is_close, hover)
        if key not in _PIL_GRADIENT_CACHE:
            img = Image.new("RGB", (width, height))
            pixels = []
            for y in range(height):
                yf = y / max(1, height - 1)
                for x in range(width):
                    if y == height - 1 or x == 0 or x == width - 1:
                        r, g, b = (22, 25, 30) if not is_close else (95, 22, 22)
                    elif y == 0 or x == 1 or x == width - 2:
                        if is_close:
                            r, g, b = (245, 165, 165) if yf < 0.5 else (215, 95, 95)
                        else:
                            r, g, b = (145, 155, 170) if yf < 0.5 else (95, 105, 120)
                    else:
                        if is_close:
                            if yf < 0.48:
                                t = yf / 0.48
                                r = int((238 if hover else 220) - t * 32)
                                g = int((125 if hover else 100) - t * 38)
                                b = int((120 if hover else 95) - t * 38)
                            else:
                                t = (yf - 0.48) / 0.52
                                r = int((185 if hover else 165) + t * 38)
                                g = int((38 if hover else 26) + t * 28)
                                b = int((34 if hover else 24) + t * 22)
                        else:
                            if yf < 0.48:
                                t = yf / 0.48
                                r = int((125 if hover else 102) - t * 24)
                                g = int((134 if hover else 110) - t * 25)
                                b = int((148 if hover else 122) - t * 26)
                            else:
                                t = (yf - 0.48) / 0.52
                                r = int((72 if hover else 54) + t * 22)
                                g = int((79 if hover else 60) + t * 24)
                                b = int((90 if hover else 70) + t * 26)
                    pixels.append((max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))))
            img.putdata(pixels)
            _cache_put_gradient(key, img)
        return ImageTk.PhotoImage(_PIL_GRADIENT_CACHE[key], master=self)

    def _bake_master_body_image(self, width: int, height: int) -> Image.Image:
        key = ("master_body_img", width, height)
        if key in _PIL_GRADIENT_CACHE:
            return _PIL_GRADIENT_CACHE[key]

        img = Image.new("RGB", (width, height))
        pixels = []
        w_f = float(max(1, width - 1))
        h_f = float(max(1, height - 1))

        for y in range(height):
            yf = y / h_f
            if yf < 0.16:
                hy = yf / 0.16
                base = 47.0 - hy * 14.0 + (1.0 - hy) ** 2 * 14.0
            elif yf > 0.88:
                fy = (yf - 0.88) / 0.12
                base = 28.0 + (fy ** 1.5) * 26.0
            else:
                base = 31.0 + yf * 6.0

            for x in range(width):
                xf = x / w_f
                val = base

                dx_tl = xf - 0.14
                dy_tl = (yf / 0.22) - 0.15
                dist_tl = dx_tl * dx_tl + dy_tl * dy_tl
                if dist_tl < 0.35:
                    val += (0.35 - dist_tl) * 42.0

                diag = xf * 0.85 + (yf / 0.45) * 0.32
                if 0.28 < diag < 0.56:
                    t = (diag - 0.42) / 0.14
                    val += (1.0 - t * t) * 14.0
                if 0.58 < diag < 0.72:
                    t = (diag - 0.65) / 0.07
                    val += (1.0 - t * t) * 9.0

                if yf > 0.86:
                    dx_b = xf - 0.48
                    glow_b = max(0.0, 1.0 - (dx_b * dx_b) * 6.5)
                    val += glow_b * 18.0

                v_int = int(val)
                r = max(0, min(255, v_int - 4))
                g = max(0, min(255, v_int))
                b = max(0, min(255, v_int + 7))
                pixels.append((r, g, b))

        img.putdata(pixels)
        _cache_put_gradient(key, img)
        return img

    def _on_shell_configure(self, event=None):
        """Instant coordinate repositioning on resize; C-stretched PIL background texture."""
        w = self.bg_canvas.winfo_width()
        h = self.bg_canvas.winfo_height()
        if w < 50 or h < 50 or (w, h) == self._last_drawn_size:
            return
        self._last_drawn_size = (w, h)

        self.bg_canvas.coords("bevel_outer", 0, 0, w - 1, h - 1)
        self.bg_canvas.coords("bevel_inner", 1, 1, w - 2, h - 2)
        self.bg_canvas.coords("bevel_top_shine", 2, 1, w - 3, 1)

        close_w, min_w = 38, 27
        close_x = w - close_w - 6
        min_x = close_x - min_w + 1
        self.bg_canvas.coords("btn_min_img", min_x, 1)
        self.bg_canvas.coords("btn_close_img", close_x, 1)

        mx = min_x + min_w // 2
        self.bg_canvas.coords("btn_min_glyph_sh", mx - 4, 11, mx + 4, 13)
        self.bg_canvas.coords("btn_min_glyph", mx - 4, 10, mx + 4, 12)

        cx = close_x + close_w // 2
        self.bg_canvas.coords("btn_close_glyph_sh", cx + 1, 10)
        self.bg_canvas.coords("btn_close_glyph", cx, 9)

        self.bg_canvas.coords("nav_settings", w - 10, 29)
        self.bg_canvas.coords("nav_sep", w - 58, 29)
        self.bg_canvas.coords("nav_mini", w - 65, 29)

        self.bg_canvas.coords("footer_counter_shadow", 13, h - 14)
        self.bg_canvas.coords("footer_counter", 12, h - 15)
        self.bg_canvas.coords("footer_reset", 82, h - 15)
        self.bg_canvas.coords("footer_pin", w - 12, h - 15)

        self._update_bg_texture(w, h)

    def _update_bg_texture(self, w: int, h: int):
        self._tex_after_id = None
        if w < 50 or h < 50:
            return
        try:
            stretched = self._master_body_img.resize((w, h), Image.Resampling.NEAREST)
            self._active_bg_photo = ImageTk.PhotoImage(stretched, master=self)
            self.bg_canvas.itemconfig("bg_img", image=self._active_bg_photo)
        except Exception:
            pass

    # =========================================================================
    # Crash-Proof Window Dragging & Throttled Edge Resizing
    # =========================================================================

    def _detect_resize_zone(self, x: int, y: int) -> Optional[str]:
        w = self.winfo_width()
        h = self.winfo_height()
        b = self.RESIZE_BORDER
        if y < 20 and x > w - 75:
            return None

        on_left = x < b
        on_right = x > w - b
        on_top = y < b
        on_bottom = y > h - b

        if on_bottom and on_right:
            return "se"
        if on_bottom and on_left:
            return "sw"
        if on_top and on_right:
            return "ne"
        if on_top and on_left:
            return "nw"
        if on_right:
            return "e"
        if on_left:
            return "w"
        if on_bottom:
            return "s"
        if on_top:
            return "n"
        return None

    def _on_canvas_motion(self, event):
        zone = self._detect_resize_zone(event.x, event.y)
        cursor_map = {
            "se": "size_nw_se",
            "nw": "size_nw_se",
            "sw": "size_ne_sw",
            "ne": "size_ne_sw",
            "e": "size_we",
            "w": "size_we",
            "s": "size_ns",
            "n": "size_ns",
        }
        new_cursor = cursor_map.get(zone, "")
        if self.bg_canvas.cget("cursor") != new_cursor:
            self.bg_canvas.configure(cursor=new_cursor)

    def _on_canvas_press(self, event):
        hit_items = self.bg_canvas.find_overlapping(event.x - 1, event.y - 1, event.x + 1, event.y + 1)
        interactive_tags = {"btn_min", "btn_close", "nav_settings", "nav_mini", "footer_reset", "footer_pin"}
        for item in hit_items:
            if interactive_tags.intersection(self.bg_canvas.gettags(item)):
                return

        zone = self._detect_resize_zone(event.x, event.y)
        self._drag_data = {
            "x": event.x_root,
            "y": event.y_root,
            "start_geo": (self.winfo_x(), self.winfo_y(), self.winfo_width(), self.winfo_height()),
            "mode": f"resize_{zone}" if zone else "move",
            "pending": False,
        }

    def _on_canvas_drag(self, event):
        mode = self._drag_data.get("mode")
        if not mode:
            return

        if mode == "move":
            dx = event.x_root - self._drag_data["x"]
            dy = event.y_root - self._drag_data["y"]
            sx, sy, _, _ = self._drag_data["start_geo"]
            nx, ny = sx + dx, sy + dy
            self._window_pos = (nx, ny)
            self.geometry(f"+{nx}+{ny}")
            return

        if mode.startswith("resize_"):
            self._drag_data["cur_x"] = event.x_root
            self._drag_data["cur_y"] = event.y_root
            if not self._drag_data.get("pending"):
                self._drag_data["pending"] = True
                self.after(24, self._apply_throttled_resize)

    def _apply_throttled_resize(self):
        self._drag_data["pending"] = False
        mode = self._drag_data.get("mode")
        if not mode or not mode.startswith("resize_"):
            return

        dx = self._drag_data.get("cur_x", self._drag_data["x"]) - self._drag_data["x"]
        dy = self._drag_data.get("cur_y", self._drag_data["y"]) - self._drag_data["y"]
        sx, sy, sw, sh = self._drag_data["start_geo"]

        z = mode.split("_")[1]
        min_w = self.MINI_WIDTH
        min_h = 185
        nx, ny, nw, nh = sx, sy, sw, sh

        if "e" in z:
            nw = max(min_w, sw + dx)
        if "s" in z:
            nh = max(min_h, sh + dy)
        if "w" in z:
            nw = max(min_w, sw - dx)
            if nw > min_w:
                nx = sx + dx
        if "n" in z:
            nh = max(min_h, sh - dy)
            if nh > min_h:
                ny = sy + dy

        self._window_pos = (nx, ny)
        self.geometry(f"{nw}x{nh}+{nx}+{ny}")

    def _on_canvas_release(self, event):
        if self._drag_data.get("mode"):
            try:
                self._window_pos = (self.winfo_x(), self.winfo_y())
                self._save_config()
            except Exception:
                pass
        self._drag_data["mode"] = None

    def _minimize_window(self):
        """Minimize cleanly to the Windows Taskbar without deadlocking Tkinter."""
        try:
            self._saved_geo = (self.winfo_width(), self.winfo_height(), self.winfo_x(), self.winfo_y())
            self._is_minimized = True
            self.overrideredirect(False)
            self.iconify()
        except Exception:
            self._is_minimized = False

    def _on_window_map(self, event=None):
        """Restore frameless overrideredirect shell when un-minimized from taskbar."""
        if event is not None and event.widget is not self:
            return
        if self._is_minimized and self.state() == "normal":
            self._is_minimized = False
            self.overrideredirect(True)
            if self._saved_geo:
                w, h, x, y = self._saved_geo
                self.geometry(f"{w}x{h}+{x}+{y}")
            self._taskbar_after_id = self.after(10, self._enable_taskbar_icon)

    # =========================================================================
    # UI Construction
    # =========================================================================

    def _build_ui(self):
        self.topmost_switch_var = tk.BooleanVar(value=False)
        self._drag_data = {"mode": None}
        self.toggle_btn = _ToggleBtnProxy(self)

        self.bg_canvas = tk.Canvas(self, bg="#232830", highlightthickness=0, bd=0)
        self.bg_canvas.place(x=0, y=0, relwidth=1.0, relheight=1.0)

        self.bg_canvas.create_image(0, 0, anchor="nw", tags="bg_img")
        self.bg_canvas.create_rectangle(0, 0, 10, 10, outline="#121418", width=1, tags="bevel_outer")
        self.bg_canvas.create_rectangle(1, 1, 9, 9, outline="#4c5464", width=1, tags="bevel_inner")
        self.bg_canvas.create_line(2, 1, 8, 1, fill="#737d90", tags="bevel_top_shine")

        # Rebranded Header Title: "LTC Auto Clicker"
        self.bg_canvas.create_text(13, 22, text="LTC Auto Clicker", font=("Segoe UI", 11, "bold"), fill="#111318", anchor="w")
        self.bg_canvas.create_text(12, 21, text="LTC Auto Clicker", font=("Segoe UI", 11, "bold"), fill="#f8fafc", anchor="w")

        self.bg_canvas.create_image(0, 1, image=self._btn_imgs["min_norm"], anchor="nw", tags=("btn_min_img", "btn_min"))
        self.bg_canvas.create_image(0, 1, image=self._btn_imgs["close_norm"], anchor="nw", tags=("btn_close_img", "btn_close"))
        self.bg_canvas.create_rectangle(0, 0, 0, 0, fill="#1e2228", outline="", tags=("btn_min_glyph_sh", "btn_min"))
        self.bg_canvas.create_rectangle(0, 0, 0, 0, fill="#ffffff", outline="", tags=("btn_min_glyph", "btn_min"))
        self.bg_canvas.create_text(0, 0, text="✕", font=("Segoe UI", 8, "bold"), fill="#450a0a", tags=("btn_close_glyph_sh", "btn_close"))
        self.bg_canvas.create_text(0, 0, text="✕", font=("Segoe UI", 8, "bold"), fill="#ffffff", tags=("btn_close_glyph", "btn_close"))

        self.bg_canvas.tag_bind("btn_min", "<Button-1>", lambda e: self._minimize_window())
        self.bg_canvas.tag_bind("btn_min", "<Enter>", lambda e: self.bg_canvas.itemconfig("btn_min_img", image=self._btn_imgs["min_hover"]))
        self.bg_canvas.tag_bind("btn_min", "<Leave>", lambda e: self.bg_canvas.itemconfig("btn_min_img", image=self._btn_imgs["min_norm"]))

        self.bg_canvas.tag_bind("btn_close", "<Button-1>", lambda e: self.destroy())
        self.bg_canvas.tag_bind("btn_close", "<Enter>", lambda e: self.bg_canvas.itemconfig("btn_close_img", image=self._btn_imgs["close_hover"]))
        self.bg_canvas.tag_bind("btn_close", "<Leave>", lambda e: self.bg_canvas.itemconfig("btn_close_img", image=self._btn_imgs["close_norm"]))

        # Pure Text Header Navigation (Zero Emojis: "Mini | Settings")
        self.bg_canvas.create_text(0, 29, text="Settings", font=("Segoe UI", 8, "bold"), fill="#e2e8f0", anchor="e", tags="nav_settings")
        self.bg_canvas.create_text(0, 29, text="|", font=("Segoe UI", 8), fill="#64748b", anchor="e", tags="nav_sep")
        self.bg_canvas.create_text(0, 29, text="Mini", font=("Segoe UI", 8, "bold"), fill="#dbe3ef", anchor="e", tags="nav_mini")

        self.bg_canvas.tag_bind("nav_settings", "<Button-1>", lambda e: self._toggle_settings_view())
        self.bg_canvas.tag_bind("nav_settings", "<Enter>", lambda e: self.bg_canvas.itemconfig("nav_settings", fill="#ffffff"))
        self.bg_canvas.tag_bind("nav_settings", "<Leave>", lambda e: self.bg_canvas.itemconfig("nav_settings", fill="#60a5fa" if self.is_settings_open else "#e2e8f0"))

        self.bg_canvas.tag_bind("nav_mini", "<Button-1>", lambda e: self._toggle_compact_mode())
        self.bg_canvas.tag_bind("nav_mini", "<Enter>", lambda e: self.bg_canvas.itemconfig("nav_mini", fill="#ffffff"))
        self.bg_canvas.tag_bind("nav_mini", "<Leave>", lambda e: self.bg_canvas.itemconfig("nav_mini", fill="#dbe3ef"))

        # Bezel Footer (Pure Crisp Text)
        self.bg_canvas.create_text(13, 0, text="Clicks: 0", font=("Segoe UI", 9, "bold"), fill="#111318", anchor="w", tags="footer_counter_shadow")
        self.bg_canvas.create_text(12, 0, text="Clicks: 0", font=("Segoe UI", 9, "bold"), fill="#e2e8f0", anchor="w", tags="footer_counter")
        self.bg_canvas.create_text(82, 0, text="Reset", font=("Segoe UI", 8, "underline"), fill="#cbd5e1", anchor="w", tags="footer_reset")
        self.bg_canvas.create_text(0, 0, text="☐ Pin Top", font=("Segoe UI", 9, "bold"), fill="#dbe3ef", anchor="e", tags="footer_pin")

        self.bg_canvas.tag_bind("footer_reset", "<Button-1>", lambda e: self._reset_counter())
        self.bg_canvas.tag_bind("footer_reset", "<Enter>", lambda e: self.bg_canvas.itemconfig("footer_reset", fill="#ffffff"))
        self.bg_canvas.tag_bind("footer_reset", "<Leave>", lambda e: self.bg_canvas.itemconfig("footer_reset", fill="#cbd5e1"))

        self.bg_canvas.tag_bind("footer_pin", "<Button-1>", lambda e: self._toggle_pin_from_bezel())
        self.bg_canvas.tag_bind("footer_pin", "<Enter>", lambda e: self.bg_canvas.itemconfig("footer_pin", fill="#ffffff"))
        self.bg_canvas.tag_bind("footer_pin", "<Leave>", lambda e: self.bg_canvas.itemconfig("footer_pin", fill="#60a5fa" if self.topmost_switch_var.get() else "#dbe3ef"))

        self.bg_canvas.bind("<Configure>", self._on_shell_configure)
        self.bg_canvas.bind("<Motion>", self._on_canvas_motion)
        self.bg_canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.bg_canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.bg_canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

        # =========================================================================
        # CENTRAL WHITE / LIGHT SLATE CARD
        # =========================================================================
        self.central_bevel = ctk.CTkFrame(
            self,
            corner_radius=2,
            fg_color="#15181e",
            border_width=1,
            border_color="#5a6578"
        )
        self.central_bevel.pack(fill="both", expand=True, padx=8, pady=(42, 28))

        self.central_card = ctk.CTkFrame(
            self.central_bevel,
            corner_radius=1,
            fg_color="#f4f6f9",
            border_width=1,
            border_color="#ffffff"
        )
        self.central_card.pack(fill="both", expand=True, padx=1, pady=1)

        # =========================================================================
        # 1. STATUS HEADLINE AREA (Top of Card)
        # =========================================================================
        self.status_header_wrap = ctk.CTkFrame(self.central_card, fg_color="transparent")
        self.status_header_wrap.pack(fill="x", padx=10, pady=(7, 2))

        self.status_top_line = ctk.CTkFrame(self.status_header_wrap, fg_color="transparent")
        self.status_top_line.pack(fill="x")

        self.status_headline = ctk.CTkLabel(
            self.status_top_line,
            text="Auto Clicker Ready...",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="normal"),
            text_color="#1e293b",
            anchor="w",
        )
        self.status_headline.pack(side="left")

        # Status badge readout on right
        self.status_pill = ctk.CTkLabel(
            self.status_top_line,
            text="READY",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            fg_color="transparent",
            text_color="#94a3b8",
        )
        self.status_pill.pack(side="right", pady=(2, 0))

        self.status_sub_line = ctk.CTkFrame(self.status_header_wrap, fg_color="transparent")
        self.status_sub_line.pack(fill="x", pady=(0, 4))

        self.status_subtext = ctk.CTkLabel(
            self.status_sub_line,
            text="100 ms interval • 10.0 CPS",
            font=ctk.CTkFont(family="Segoe UI", size=9),
            text_color="#64748b",
            anchor="w",
        )
        self.status_subtext.pack(side="left")

        self.countdown_label = ctk.CTkLabel(
            self.status_sub_line,
            text="Next: Ready",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color="#475569",
        )

        # Crisp 1px separator line beneath status headline
        self.header_divider = ctk.CTkFrame(self.status_header_wrap, height=1, fg_color="#d5dde7")
        self.header_divider.pack(fill="x", pady=(1, 0))

        # =========================================================================
        # 2. BOTTOM ACTION TRAY (Pinned Circular Action Badge)
        # =========================================================================
        self.action_well = ctk.CTkFrame(self.central_card, fg_color="transparent", corner_radius=0)
        self.action_well.pack(fill="x", side="bottom", padx=10, pady=(4, 8))

        self.action_tray_canvas = tk.Canvas(
            self.action_well,
            height=44,
            bg="#f4f6f9",
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.action_tray_canvas.pack(fill="x", expand=True)
        self.action_tray_canvas.bind("<Configure>", lambda e: self._redraw_action_tray())
        self.action_tray_canvas.bind("<ButtonPress-1>", lambda e: self._toggle_clicking())
        self.action_tray_canvas.bind("<Enter>", self._on_tray_enter)
        self.action_tray_canvas.bind("<Leave>", self._on_tray_leave)

        # =========================================================================
        # 3. SUB-CARD A: Standard Clicker Speed Controls (Recessed Gradient Wells)
        # =========================================================================
        self.speed_card = ctk.CTkFrame(self.central_card, fg_color="transparent")
        self.speed_card.pack(fill="x", padx=10, pady=(4, 2))

        self.input_row = ctk.CTkFrame(self.speed_card, fg_color="transparent")
        self.input_row.pack(fill="x")

        ctk.CTkLabel(
            self.input_row,
            text="Speed:",
            width=44,
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#475569"
        ).pack(side="left")

        self.speed_entry = ctk.CTkEntry(
            self.input_row,
            width=50,
            height=21,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color="#ffffff",
            text_color="#0f172a",
            border_color="#b0bed1",
            border_width=1,
            corner_radius=1,
            justify="center"
        )
        self.speed_entry.insert(0, "100")
        self.speed_entry.bind("<KeyRelease>", self._on_speed_entry_change)
        self.speed_entry.bind("<FocusOut>", self._normalize_speed_entry)
        self.speed_entry.bind("<Return>", lambda e: (self._normalize_speed_entry(), self.focus_set()))
        self.speed_entry.bind("<Escape>", lambda e: (self._normalize_speed_entry(), self.focus_set()))
        self.speed_entry.pack(side="left", padx=(2, 5))

        self.unit_segmented = AeroSegmentedButton(
            self.input_row,
            values=["ms", "CPS"],
            command=self._on_unit_change,
            height=21,
            pad_x=9,
        )
        self.unit_segmented.set("ms")
        self.unit_segmented.pack(side="left")

        self.speed_info_label = ctk.CTkLabel(
            self.input_row,
            text="10.0 CPS",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color="#64748b"
        )
        self.speed_info_label.pack(side="right")

        self.speed_slider = AeroSlider(
            self.speed_card,
            from_=1,
            to=1000,
            height=16,
            command=self._on_slider_change
        )
        self.speed_slider.set(100)
        self.speed_slider.pack(fill="x", pady=(4, 1))

        self.slow_presets_frame = ctk.CTkFrame(self.speed_card, fg_color="transparent")

        slow_row1 = ctk.CTkFrame(self.slow_presets_frame, fg_color="transparent")
        slow_row1.pack(fill="x")

        ctk.CTkLabel(
            slow_row1,
            text="Preset:",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#475569"
        ).pack(side="left")

        self.main_slow_preset_segmented = AeroSegmentedButton(
            slow_row1,
            values=["Very Slow", "Slow", "Fast"],
            command=self._on_slow_preset_change,
            height=21,
            pad_x=8,
        )
        self.main_slow_preset_segmented.set("Fast")
        self.main_slow_preset_segmented.pack(side="right")

        slow_row2 = ctk.CTkFrame(self.slow_presets_frame, fg_color="transparent")
        slow_row2.pack(fill="x", pady=(3, 0))

        self.slow_preset_info_label = ctk.CTkLabel(
            slow_row2,
            text="100 ms Standard (10 CPS)",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color="#334155"
        )
        self.slow_preset_info_label.pack(side="left")

        # =========================================================================
        # 4. SUB-CARD B: Options & Keybind Container (Recessed Gradient Wells)
        # =========================================================================
        self.opts_card = ctk.CTkFrame(self.central_card, fg_color="transparent")
        self.opts_card.pack(fill="x", padx=10, pady=(1, 4))

        self.row1 = ctk.CTkFrame(self.opts_card, fg_color="transparent")
        self.row1.pack(fill="x", pady=(2, 3))

        self.btn_label = ctk.CTkLabel(
            self.row1,
            text="Button:",
            width=44,
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#475569"
        )
        self.btn_label.pack(side="left")

        self.btn_segmented = AeroSegmentedButton(
            self.row1,
            values=["Left", "Right", "Mid"],
            command=self._on_mouse_button_change,
            height=21,
            pad_x=8,
        )
        self.btn_segmented.set("Left")
        self.btn_segmented.pack(side="left", padx=2)

        self.target_key_btn = AeroKeycapButton(
            self.row1,
            text="Space • Key",
            width=86,
            height=21,
            style="steel",
            font_size=8,
            command=self._begin_target_key_capture
        )

        self.hotkey_btn = AeroKeycapButton(
            self.row1,
            text="F6 • Bind",
            width=76,
            height=21,
            style="keycap",
            font_size=8,
            command=self._begin_hotkey_capture
        )
        self.hotkey_btn.pack(side="right")

        ctk.CTkLabel(
            self.row1,
            text="Key:",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color="#64748b"
        ).pack(side="right", padx=(0, 4))

        self.row2 = ctk.CTkFrame(self.opts_card, fg_color="transparent")
        self.row2.pack(fill="x", pady=(2, 2))

        self.type_label = ctk.CTkLabel(
            self.row2,
            text="Type:",
            width=44,
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#475569"
        )
        self.type_label.pack(side="left")

        self.type_segmented = AeroSegmentedButton(
            self.row2,
            values=["Single", "Double"],
            command=self._on_click_type_change,
            height=21,
            pad_x=9,
        )
        self.type_segmented.set("Single")
        self.type_segmented.pack(side="left", padx=2)

        self.key_presser_info_label = ctk.CTkLabel(
            self.row2,
            text="Repeats selected key",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color="#334155"
        )

        self.jitter_switch = AeroCheckBox(
            self.row2,
            text="Jitter (±10%)",
            command=self._on_jitter_toggle
        )
        self.jitter_switch.pack(side="right")

        # =========================================================================
        # 5. IN-CARD SETTINGS VIEW (Consistent Sharp Corners & Gradient Controls)
        # =========================================================================
        self.settings_card = ctk.CTkFrame(self.central_card, fg_color="transparent")

        settings_hdr = ctk.CTkFrame(self.settings_card, fg_color="transparent")
        settings_hdr.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(
            settings_hdr,
            text="Settings & Advanced",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#1e293b"
        ).pack(side="left")

        self.settings_back_btn = AeroKeycapButton(
            settings_hdr,
            text="← Back",
            width=54,
            height=20,
            style="steel",
            font_size=8,
            command=self._toggle_settings_view
        )
        self.settings_back_btn.pack(side="right")

        mode_row = ctk.CTkFrame(self.settings_card, fg_color="transparent")
        mode_row.pack(fill="x", pady=(2, 3))

        ctk.CTkLabel(
            mode_row,
            text="Mode:",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#475569"
        ).pack(side="left")

        self.mode_segmented = AeroSegmentedButton(
            mode_row,
            values=["Clicker", "Key Presser"],
            command=self._on_mode_change,
            height=21,
            pad_x=7,
        )
        self.mode_segmented.set("Clicker")
        self.mode_segmented.pack(side="right")

        trig_row = ctk.CTkFrame(self.settings_card, fg_color="transparent")
        trig_row.pack(fill="x", pady=(2, 3))

        ctk.CTkLabel(
            trig_row,
            text="Activation:",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#475569"
        ).pack(side="left")

        self.trigger_segmented = AeroSegmentedButton(
            trig_row,
            values=["Toggle", "Hold Key"],
            command=self._on_trigger_mode_change,
            height=21,
            pad_x=10,
        )
        self.trigger_segmented.set("Toggle")
        self.trigger_segmented.pack(side="right")

        adv_inputs_row = ctk.CTkFrame(self.settings_card, fg_color="transparent")
        adv_inputs_row.pack(fill="x", pady=(2, 3))

        ctk.CTkLabel(
            adv_inputs_row,
            text="Hold:",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#475569"
        ).pack(side="left")

        self.hold_entry = ctk.CTkEntry(
            adv_inputs_row,
            width=38,
            height=21,
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            fg_color="#ffffff",
            text_color="#0f172a",
            border_color="#b0bed1",
            border_width=1,
            corner_radius=1,
            justify="center"
        )
        self.hold_entry.insert(0, "15")
        self.hold_entry.bind("<KeyRelease>", self._on_hold_change)
        self.hold_entry.bind("<FocusOut>", self._normalize_hold_entry)
        self.hold_entry.bind("<Return>", lambda e: (self._normalize_hold_entry(), self.focus_set()))
        self.hold_entry.bind("<Escape>", lambda e: (self._normalize_hold_entry(), self.focus_set()))
        self.hold_entry.pack(side="left", padx=(4, 2))

        ctk.CTkLabel(
            adv_inputs_row,
            text="ms",
            font=ctk.CTkFont(family="Segoe UI", size=9),
            text_color="#64748b"
        ).pack(side="left")

        self.limit_entry = ctk.CTkEntry(
            adv_inputs_row,
            width=44,
            height=21,
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            fg_color="#ffffff",
            text_color="#0f172a",
            border_color="#b0bed1",
            border_width=1,
            corner_radius=1,
            justify="center"
        )
        self.limit_entry.insert(0, "0")
        self.limit_entry.bind("<KeyRelease>", self._on_limit_change)
        self.limit_entry.bind("<FocusOut>", self._normalize_limit_entry)
        self.limit_entry.bind("<Return>", lambda e: (self._normalize_limit_entry(), self.focus_set()))
        self.limit_entry.bind("<Escape>", lambda e: (self._normalize_limit_entry(), self.focus_set()))
        self.limit_entry.pack(side="right")

        ctk.CTkLabel(
            adv_inputs_row,
            text="Limit:",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#475569"
        ).pack(side="right", padx=(0, 4))

        # Row: Corner Panic + Audio Beep
        panic_row = ctk.CTkFrame(self.settings_card, fg_color="transparent")
        panic_row.pack(fill="x", pady=(2, 2))

        self.panic_switch = AeroCheckBox(
            panic_row,
            text="Corner Panic (0, 0)",
            command=self._on_panic_toggle
        )
        self.panic_switch.pack(side="left")

        self.sound_switch = AeroCheckBox(
            panic_row,
            text="Audio Beep",
            command=self._on_sound_toggle
        )
        self.sound_switch.pack(side="right")

        # Row: Lock Target Position + Pick (X, Y) Button
        lock_row = ctk.CTkFrame(self.settings_card, fg_color="transparent")
        lock_row.pack(fill="x", pady=(1, 2))

        self.lock_pos_switch = AeroCheckBox(
            lock_row,
            text="Lock Target Position",
            command=self._on_lock_pos_toggle
        )
        self.lock_pos_switch.pack(side="left")

        self.pick_pos_btn = AeroKeycapButton(
            lock_row,
            text="Pick (X, Y)",
            width=84,
            height=19,
            style="keycap",
            font_size=8,
            command=self._begin_pick_position
        )
        self.pick_pos_btn.pack(side="right")

        scatter_row = ctk.CTkFrame(self.settings_card, fg_color="transparent")
        scatter_row.pack(fill="x", pady=(1, 2))

        self.central_scatter_switch = AeroCheckBox(
            scatter_row,
            text="Central Scatter (8 rotating spots)",
            command=self._on_central_scatter_toggle
        )
        self.central_scatter_switch.pack(side="left")

        slow_mode_row = ctk.CTkFrame(self.settings_card, fg_color="transparent")
        slow_mode_row.pack(fill="x", pady=(1, 2))

        self.slow_presets_switch = AeroCheckBox(
            slow_mode_row,
            text="Slow Presets Mode (Experimental)",
            command=self._on_slow_presets_toggle
        )
        self.slow_presets_switch.pack(side="left")

        self.settings_preset_row = ctk.CTkFrame(self.settings_card, fg_color="transparent")

        ctk.CTkLabel(
            self.settings_preset_row,
            text="Preset Speed:",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color="#475569"
        ).pack(side="left")

        self.settings_slow_preset_segmented = AeroSegmentedButton(
            self.settings_preset_row,
            values=["Very Slow", "Slow", "Fast"],
            command=self._on_slow_preset_change,
            height=20,
            pad_x=7,
        )
        self.settings_slow_preset_segmented.set("Fast")
        self.settings_slow_preset_segmented.pack(side="right")

        self.footer_sub_row = ctk.CTkFrame(self.settings_card, fg_color="transparent")
        self.footer_sub_row.pack(fill="x", pady=(4, 0))

        ctk.CTkLabel(
            self.footer_sub_row,
            text="Profile: %LOCALAPPDATA%",
            font=ctk.CTkFont(family="Segoe UI", size=8),
            text_color="#94a3b8"
        ).pack(side="left")

        self.reset_all_btn = AeroKeycapButton(
            self.footer_sub_row,
            text="Reset Defaults",
            width=78,
            height=20,
            style="danger",
            font_size=8,
            command=self._reset_all_settings
        )
        self.reset_all_btn.pack(side="right")

        ToolTip(self.jitter_switch, "Adds ±10% random variation to the interval between clicks or key presses")
        ToolTip(self.mode_segmented, "Clicker: Mouse auto clicker • Key Presser: Keyboard key spammer")
        ToolTip(self.target_key_btn, "Click, then press any keyboard key (Space, E, Backspace, Enter, etc.) to set the key to repeat")
        ToolTip(self.central_scatter_switch, "Moves the system cursor among 8 positions around the primary screen center")
        ToolTip(self.slow_presets_switch, "Disables custom speed input and enables AFK slow presets: Very Slow (5m), Slow (1m), Fast (100ms)")
        ToolTip(self.main_slow_preset_segmented, "Very Slow (every 5m) • Slow (every 1m) • Fast (100ms standard)")
        ToolTip(self.settings_slow_preset_segmented, "Very Slow (every 5m) • Slow (every 1m) • Fast (100ms standard)")
        ToolTip(self.trigger_segmented, "Toggle: Tap key to start/stop • Hold Key: Active while key is held")
        ToolTip(self.hold_entry, "Mouse button or key press duration in milliseconds (15ms default)")
        ToolTip(self.limit_entry, "Max clicks/presses before auto-stopping (0 = infinite)")
        ToolTip(self.panic_switch, "Stops when the mouse touches the main screen's top-left corner (0, 0). The Pause key always stops, even with this off")
        ToolTip(self.sound_switch, "Play a subtle short tone when starting or stopping")
        ToolTip(self.lock_pos_switch, "Lock clicks to a fixed screen coordinate instead of following the cursor")
        ToolTip(self.pick_pos_btn, "Click, then left-click anywhere on screen to lock that target (X, Y) coordinate")
        ToolTip(self.reset_all_btn, "Reset all settings & hotkeys to factory defaults")
        ToolTip(self.hotkey_btn, "Click, then press any keyboard key or Mouse 4 / Mouse 5 / Middle Click to bind")

    # =========================================================================
    # Aero Action Tray Rendering (Zero Pixel Shift)
    # =========================================================================

    def _on_tray_enter(self, event=None):
        self._tray_hover = True
        self._redraw_action_tray()

    def _on_tray_leave(self, event=None):
        self._tray_hover = False
        self._redraw_action_tray()

    def _redraw_action_tray(self):
        if not hasattr(self, "action_tray_canvas") or not self.action_tray_canvas.winfo_exists():
            return
        w = self.action_tray_canvas.winfo_width()
        h = 44
        if w < 40:
            w = 305

        self.action_tray_canvas.delete("all")

        stops = self.TRAY_HOVER_STOPS if self._tray_hover else self.TRAY_NORM_STOPS
        border_c = (180, 192, 208) if self._tray_hover else (205, 213, 223)
        tray_pil = _bake_rect_gradient_pil(
            w,
            h,
            stops,
            border_color=border_c,
            top_shine=(255, 255, 255),
            bg_corner=(244, 246, 249),
        )
        self._tray_photos["bg"] = ImageTk.PhotoImage(tray_pil, master=self)
        self.action_tray_canvas.create_image(0, 0, image=self._tray_photos["bg"], anchor="nw")

        is_running = self.engine.is_running
        is_key = (self.active_mode == "key_presser")
        is_hold = (self.hotkey_listener.trigger_mode == "hold")
        hotkey = self.hotkey_listener.key_name

        if is_running:
            badge_key = "badge_stop_hover" if self._tray_hover else "badge_stop_norm"
            title_txt = "Stop key presser" if is_key else "Stop clicking"
            sub_txt = f"Release {hotkey} to halt" if is_hold else f"Press {hotkey} to halt"
        else:
            badge_key = "badge_start_hover" if self._tray_hover else "badge_start_norm"
            title_txt = "Start key presser" if is_key else "Start clicking"
            sub_txt = f"Hold {hotkey} to activate" if is_hold else f"Press {hotkey} to activate"

        cx = w // 2
        badge_x = cx - 64
        text_x = cx - 42

        self.action_tray_canvas.create_image(
            badge_x, h // 2, image=self._btn_imgs[badge_key], anchor="center"
        )
        self.action_tray_canvas.create_text(
            text_x,
            15,
            text=title_txt,
            font=("Segoe UI Semibold", 10),
            fill="#000000" if self._tray_hover else "#1e293b",
            anchor="w",
        )
        self.action_tray_canvas.create_text(
            text_x,
            30,
            text=sub_txt,
            font=("Segoe UI", 8),
            fill="#64748b",
            anchor="w",
        )

    def _tick_session_timer(self):
        self._session_timer_after_id = None
        if not self.winfo_exists() or not self.engine.is_running:
            return
        self._refresh_status_summary()
        self._session_timer_after_id = self.after(250, self._tick_session_timer)

    def _refresh_status_summary(self):
        """Update the Aero status headline, live elapsed session timer, & subtext cleanly."""
        if not hasattr(self, "status_headline") or not self.winfo_exists():
            return

        is_running = self.engine.is_running
        is_key = (self.active_mode == "key_presser")

        if self._input_error and not is_running:
            self.status_headline.configure(
                text="Input Blocked...",
                font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
                text_color="#b91c1c",
            )
            self.status_pill.configure(text="ERROR", text_color="#b91c1c")
            return

        if is_running:
            headline = "Key pressing in progress..." if is_key else "Clicking in progress..."
            self.status_headline.configure(
                text=headline,
                font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
                text_color="#0f172a",
            )
            self.status_pill.configure(text="ACTIVE", text_color="#b45309")
        else:
            headline = "Key Presser Ready..." if is_key else "Auto Clicker Ready..."
            self.status_headline.configure(
                text=headline,
                font=ctk.CTkFont(family="Segoe UI", size=15, weight="normal"),
                text_color="#1e293b",
            )
            self.status_pill.configure(text="READY", text_color="#94a3b8")

        elapsed_str = _format_elapsed_mmss(self.engine.get_session_elapsed()) if is_running else ""

        if getattr(self.engine, "slow_presets", False):
            choice = getattr(self.engine, "slow_preset_choice", "fast")
            desc = "5-Min (300s)" if choice == "very_slow" else ("1-Min (60s)" if choice == "slow" else "100 ms (10 CPS)")
            if is_key:
                tkey = getattr(self.engine, "target_key", "Space")
                if is_running:
                    self.status_subtext.configure(text=f"{elapsed_str} elapsed • [{tkey}] • {desc}")
                else:
                    self.status_subtext.configure(text=f"Target [{tkey}] • AFK {desc}")
            else:
                if is_running:
                    self.status_subtext.configure(text=f"{elapsed_str} elapsed • {desc}")
                else:
                    self.status_subtext.configure(text=f"AFK Preset • {desc} interval")
        else:
            ms = self.engine.interval_sec * 1000.0
            cps = 1000.0 / max(1.0, ms)
            if is_key:
                tkey = getattr(self.engine, "target_key", "Space")
                if is_running:
                    self.status_subtext.configure(text=f"{elapsed_str} elapsed • [{tkey}] ({cps:.1f}/s)")
                else:
                    self.status_subtext.configure(text=f"Target [{tkey}] • {ms:.0f} ms ({cps:.1f}/s)")
            else:
                if is_running:
                    self.status_subtext.configure(text=f"{elapsed_str} elapsed • {cps:.1f} CPS ({ms:.0f} ms)")
                else:
                    self.status_subtext.configure(text=f"{ms:.0f} ms interval • {cps:.1f} CPS")

    # =========================================================================
    # Mode Switching & Layout Transitions
    # =========================================================================

    def _refresh_bezel_labels(self):
        if not hasattr(self, "bg_canvas") or not self.winfo_exists():
            return
        if self.active_mode == "key_presser":
            clicks_text = f"Keys: {self.engine.total_clicks:,}"
        else:
            clicks_text = f"Clicks: {self.engine.total_clicks:,}"
        self.bg_canvas.itemconfig("footer_counter", text=clicks_text)
        self.bg_canvas.itemconfig("footer_counter_shadow", text=clicks_text)

        mini_text = "Full" if self.is_compact_mode else "Mini"
        self.bg_canvas.itemconfig("nav_mini", text=mini_text)
        self.bg_canvas.itemconfig("nav_settings", fill="#60a5fa" if self.is_settings_open else "#e2e8f0")

        is_pinned = bool(self.topmost_switch_var.get())
        pin_mark = "☑" if is_pinned else "☐"
        self.bg_canvas.itemconfig("footer_pin", text=f"{pin_mark} Pin Top", fill="#60a5fa" if is_pinned else "#dbe3ef")

    _KEY_ALIASES = {
        "space": "Space",
        "BackSpace": "Backspace",
        "Return": "Enter",
        "Tab": "Tab",
        "Delete": "Delete",
        "Insert": "Insert",
        "Home": "Home",
        "End": "End",
        "Prior": "Page Up",
        "Next": "Page Down",
        "Up": "Up",
        "Down": "Down",
        "Left": "Left",
        "Right": "Right",
        "Scroll_Lock": "Scroll Lock",
        "Shift_L": "Shift",
        "Shift_R": "Shift",
        "Control_L": "Ctrl",
        "Control_R": "Ctrl",
        "Alt_L": "Alt",
        "Alt_R": "Alt",
    }

    def _cancel_active_captures(self):
        if self._picking_pos:
            self._end_pick_position()
        if self._capturing_target_key:
            self._end_target_key_capture()
        if self._capturing_hotkey:
            self._end_hotkey_capture()

    def _clamp_to_monitor(self, wx: int, wy: int, width: int, height: int) -> Tuple[int, int]:
        """Keep the window inside the work area of the monitor nearest to it (no gaps between monitors)."""
        area = _nearest_monitor_work_area(wx + width // 2, wy + height // 2)
        if area is not None:
            left, top, right, bottom = area
            wx = max(left + 10, min(wx, max(left + 10, right - width - 10)))
            wy = max(top + 10, min(wy, max(top + 10, bottom - height - 10)))
            return wx, wy
        try:
            user32 = ctypes.windll.user32
            vx = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
            vy = user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
            vw = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
            vh = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
            if vw <= 0 or vh <= 0:
                vx, vy = 0, 0
                vw = self.winfo_screenwidth()
                vh = self.winfo_screenheight()
            wx = max(vx + 10, min(wx, max(vx + 10, vx + vw - width - 10)))
            wy = max(vy + 10, min(wy, max(vy + 10, vy + vh - height - 40)))
        except Exception:
            pass
        return wx, wy

    def _on_mode_change(self, mode: str):
        self._cancel_active_captures()
        clean_mode = str(mode).strip()
        if clean_mode in ("Key Presser", "key_presser"):
            self.active_mode = "key_presser"
            self.engine.mode = "key_presser"

            # Ensure target key never collides with the active start/stop hotkey
            if self.engine.target_key_vk == self.hotkey_vk_code:
                alt_name, alt_vk = ("E", 0x45) if self.hotkey_vk_code == 0x20 else ("Space", 0x20)
                self.engine.target_key = alt_name
                self.engine.target_key_vk = alt_vk

            if not self.is_settings_open:
                if not self.is_compact_mode:
                    self.speed_card.pack(fill="x", padx=10, pady=(4, 2), before=self.opts_card)
                else:
                    self.speed_card.pack(fill="x", padx=10, pady=(4, 2))

            self.btn_segmented.pack_forget()
            self.btn_label.configure(text="Target:", width=44)
            self.target_key_btn.configure(text=f"{self.engine.target_key} • Key")
            self.target_key_btn.pack(side="left", padx=2)

            self.type_label.pack_forget()
            self.type_segmented.pack_forget()
            self.key_presser_info_label.pack(side="left")
            self.row2.pack(fill="x", pady=(2, 2))

            if self.engine.slow_presets and self.engine.get_effective_interval() >= 5.0 and not self.is_settings_open:
                self.countdown_label.configure(text="Next: Ready")
                self.countdown_label.pack(side="right")
            else:
                self.countdown_label.pack_forget()
        else:
            self.active_mode = "clicker"
            self.engine.mode = "clicker"

            if not self.is_settings_open:
                if not self.is_compact_mode:
                    self.speed_card.pack(fill="x", padx=10, pady=(4, 2), before=self.opts_card)
                else:
                    self.speed_card.pack(fill="x", padx=10, pady=(4, 2))

            self.target_key_btn.pack_forget()
            self.btn_label.configure(text="Button:", width=44)
            self.btn_segmented.pack(side="left", padx=2)

            self.key_presser_info_label.pack_forget()
            self.type_label.pack(side="left")
            self.type_segmented.pack(side="left", padx=2)
            self.row2.pack(fill="x", pady=(2, 2))

            if self.engine.slow_presets and self.engine.get_effective_interval() >= 5.0 and not self.is_settings_open:
                self.countdown_label.configure(text="Next: Ready")
                self.countdown_label.pack(side="right")
            else:
                self.countdown_label.pack_forget()

        self._refresh_status_summary()
        self._redraw_action_tray()
        self._refresh_bezel_labels()
        self._save_config()
        if not self.is_settings_open:
            self._schedule_fit_window()

    def _toggle_compact_mode(self):
        self._cancel_active_captures()
        if self.is_settings_open:
            self._toggle_settings_view()

        self.is_compact_mode = not self.is_compact_mode
        if self.is_compact_mode:
            self.opts_card.pack_forget()
            self.speed_slider.pack_forget()
        else:
            if not getattr(self.engine, "slow_presets", False):
                self.speed_slider.pack(fill="x", pady=(4, 1))
            self.opts_card.pack(fill="x", padx=10, pady=(1, 4), before=self.action_well)

        self._refresh_bezel_labels()
        self._schedule_fit_window()

    def _toggle_settings_view(self):
        self._cancel_active_captures()

        self.is_settings_open = not self.is_settings_open

        if self.is_settings_open:
            self.status_header_wrap.pack_forget()
            self.speed_card.pack_forget()
            self.opts_card.pack_forget()
            self.action_well.pack_forget()
            self.settings_card.pack(fill="x", padx=10, pady=6)
        else:
            self.settings_card.pack_forget()
            self._save_config()

            self.status_header_wrap.pack(fill="x", padx=10, pady=(7, 2))
            self.action_well.pack(fill="x", side="bottom", padx=10, pady=(4, 8))

            self.speed_card.pack(fill="x", padx=10, pady=(4, 2))
            if self.engine.slow_presets and self.engine.get_effective_interval() >= 5.0:
                self.countdown_label.pack(side="right")
            else:
                self.countdown_label.pack_forget()

            if not self.is_compact_mode:
                self.opts_card.pack(fill="x", padx=10, pady=(1, 4))

            self._on_state_change(self.engine.is_running)

        self._refresh_bezel_labels()
        self._schedule_fit_window()

    def _fit_window_to_content(self):
        self._fit_after_id = None
        if not self.winfo_exists():
            return
        self.update_idletasks()
        if self.is_settings_open:
            width = self.NORMAL_WIDTH
            extra_height = 6
        elif self.is_compact_mode:
            width = self.MINI_WIDTH
            extra_height = self.DEFAULT_VERTICAL_BREATHING_ROOM
        else:
            width = self.NORMAL_WIDTH
            extra_height = self.DEFAULT_VERTICAL_BREATHING_ROOM
        height = self.central_bevel.winfo_reqheight() + 70 + extra_height
        self.minsize(width, height)
        if self._window_pos is not None:
            wx, wy = self._clamp_to_monitor(self._window_pos[0], self._window_pos[1], width, height)
            self._window_pos = (wx, wy)
            self.geometry(f"{width}x{height}+{wx}+{wy}")
        else:
            try:
                sw = self.winfo_screenwidth()
                sh = self.winfo_screenheight()
                cx = max(10, (sw - width) // 2)
                cy = max(10, (sh - height) // 2)
                self.geometry(f"{width}x{height}+{cx}+{cy}")
                self._window_pos = (cx, cy)
            except Exception:
                self.geometry(f"{width}x{height}")

    # =========================================================================
    # Callbacks & State Handlers
    # =========================================================================

    def _toggle_clicking(self):
        self._cancel_active_captures()
        self.engine.toggle()
        if self.sound_enabled:
            try:
                winsound.Beep(1000 if self.engine.is_running else 600, 70)
            except Exception:
                pass

    def _queue_ui_call(self, fn: Callable[[], None]):
        """Run fn on the Tk main thread via the event queue (safe to call from the hotkey thread)."""
        self._event_queue.put(("call", fn))
        if threading.current_thread() == threading.main_thread():
            self._drain_event_queue()

    def _on_hotkey_trigger(self):
        self._queue_ui_call(self._toggle_clicking)

    def _on_hotkey_press(self):
        def action():
            if not self.engine.is_running:
                self.engine.start()
                if self.sound_enabled:
                    try:
                        winsound.Beep(1000, 70)
                    except Exception:
                        pass
        self._queue_ui_call(action)

    def _on_hotkey_release(self):
        def action():
            if self.engine.is_running:
                self.engine.stop()
                if self.sound_enabled:
                    try:
                        winsound.Beep(600, 70)
                    except Exception:
                        pass
        self._queue_ui_call(action)

    def _on_trigger_mode_change(self, mode_val: str):
        mode = "hold" if mode_val == "Hold Key" else "toggle"
        self.hotkey_listener.set_trigger_mode(mode)
        self._on_state_change(self.engine.is_running)
        self._save_config()

    def _on_panic_toggle(self):
        self.engine.panic_corner = bool(self.panic_switch.get())
        self._save_config()

    def _on_sound_toggle(self):
        self.sound_enabled = bool(self.sound_switch.get())
        self._save_config()

    def _on_lock_pos_toggle(self):
        is_locked = bool(self.lock_pos_switch.get())
        self.engine.lock_cursor_pos = is_locked
        if is_locked and self.central_scatter_switch.get():
            self.central_scatter_switch.deselect()
            self.engine.central_scatter = False
        self._update_pick_pos_btn_label()
        self._save_config()

    def _update_pick_pos_btn_label(self):
        if self.engine.locked_pos and self.engine.locked_pos[0] >= 0 and self.engine.locked_pos[1] >= 0:
            lx, ly = self.engine.locked_pos
            self.pick_pos_btn.configure(
                text=f"{lx}, {ly}",
                fg_color="#334155" if self.engine.lock_cursor_pos else "#e2e6ed",
            )
        else:
            self.pick_pos_btn.configure(text="Pick (X, Y)", fg_color="#e2e6ed")

    def _begin_pick_position(self):
        if self._picking_pos:
            self._end_pick_position()
            return
        self._picking_pos = True
        self.pick_pos_btn.configure(text="Click target…", fg_color="#334155")
        # Wait until initial mouse click on the Pick button is released
        self._pick_wait_release = True
        self._poll_pick_position()

    def _poll_pick_position(self):
        self._pick_pos_after_id = None
        if not self._picking_pos or not self.winfo_exists():
            return

        user32 = ctypes.windll.user32
        # Check Escape to cancel
        if user32.GetAsyncKeyState(0x1B) & 0x8000:
            self._end_pick_position()
            return

        lbutton_down = bool(user32.GetAsyncKeyState(0x01) & 0x8000)
        if self._pick_wait_release:
            if not lbutton_down:
                self._pick_wait_release = False
            self._pick_pos_after_id = self.after(20, self._poll_pick_position)
            return

        pt = wintypes.POINT()
        if user32.GetCursorPos(ctypes.byref(pt)):
            self.pick_pos_btn.configure(text=f"{pt.x}, {pt.y}", fg_color="#334155")
            if lbutton_down:
                # If the user clicked inside the AutoClicker window itself, cancel rather than locking onto our own GUI
                if self.engine._is_point_over_protected_window(pt.x, pt.y):
                    self._end_pick_position()
                    return
                self.engine.locked_pos = (pt.x, pt.y)
                self.engine.lock_cursor_pos = True
                self.lock_pos_switch.select()
                if self.central_scatter_switch.get():
                    self.central_scatter_switch.deselect()
                    self.engine.central_scatter = False
                self._end_pick_position()
                self._save_config()
                return

        self._pick_pos_after_id = self.after(25, self._poll_pick_position)

    def _end_pick_position(self):
        self._picking_pos = False
        if self._pick_pos_after_id:
            try:
                self.after_cancel(self._pick_pos_after_id)
            except Exception:
                pass
            self._pick_pos_after_id = None
        self._update_pick_pos_btn_label()

    def _on_central_scatter_toggle(self):
        is_scatter = bool(self.central_scatter_switch.get())
        self.engine.central_scatter = is_scatter
        if is_scatter and self.lock_pos_switch.get():
            self.lock_pos_switch.deselect()
            self.engine.lock_cursor_pos = False
            self._update_pick_pos_btn_label()
        self._save_config()

    def _on_slow_presets_toggle(self):
        is_slow = bool(self.slow_presets_switch.get())
        self.engine.slow_presets = is_slow
        self._update_slow_presets_ui_visibility()
        self._on_state_change(self.engine.is_running)
        self._save_config()

    def _on_slow_preset_change(self, val: str):
        mapping = {
            "Very Slow": "very_slow",
            "Slow": "slow",
            "Fast": "fast"
        }
        choice = mapping.get(val, "fast")
        self.engine.slow_preset_choice = choice
        self.main_slow_preset_segmented.set(val)
        self.settings_slow_preset_segmented.set(val)
        self._update_slow_preset_label(choice)
        self._on_state_change(self.engine.is_running)
        self._save_config()

    def _update_slow_preset_label(self, choice: str):
        if choice == "very_slow":
            self.slow_preset_info_label.configure(text="5-Min AFK Interval (300s)", text_color="#334155")
        elif choice == "slow":
            self.slow_preset_info_label.configure(text="1-Min Interval (60s)", text_color="#334155")
        else:
            self.slow_preset_info_label.configure(text="100 ms Standard (10 CPS)", text_color="#334155")
        self._refresh_status_summary()

    def _update_slow_presets_ui_visibility(self):
        is_slow = getattr(self.engine, "slow_presets", False)
        if is_slow:
            self.input_row.pack_forget()
            self.speed_slider.pack_forget()
            self.slow_presets_frame.pack(fill="x", pady=(2, 2))
            if hasattr(self, "settings_preset_row") and hasattr(self, "footer_sub_row"):
                self.settings_preset_row.pack(fill="x", pady=(1, 4), before=self.footer_sub_row)
        else:
            self.slow_presets_frame.pack_forget()
            self.input_row.pack(fill="x")
            if not self.is_compact_mode:
                self.speed_slider.pack(fill="x", pady=(4, 1))
            if hasattr(self, "settings_preset_row"):
                self.settings_preset_row.pack_forget()

        if hasattr(self, "countdown_label"):
            if self.active_mode in ("clicker", "key_presser"):
                if is_slow and self.engine.get_effective_interval() >= 5.0:
                    if not self.countdown_label.winfo_ismapped():
                        self.countdown_label.configure(text="Next: Ready")
                        self.countdown_label.pack(side="right")
                else:
                    self.countdown_label.pack_forget()
        self._refresh_status_summary()
        if not self.is_settings_open:
            self._schedule_fit_window()

    def _on_hold_change(self, event=None):
        try:
            val = int(self.hold_entry.get())
            self.engine.hold_duration_sec = max(1, val) / 1000.0
            self._save_config()
        except ValueError:
            pass

    def _normalize_hold_entry(self, event=None):
        try:
            val = max(1, int(self.hold_entry.get()))
        except ValueError:
            val = max(1, int(round(self.engine.hold_duration_sec * 1000.0)))
        self.hold_entry.delete(0, "end")
        self.hold_entry.insert(0, str(val))
        self.engine.hold_duration_sec = val / 1000.0
        self._save_config()

    def _on_limit_change(self, event=None):
        try:
            val = int(self.limit_entry.get())
            self.engine.click_limit = max(0, val)
            self._save_config()
        except ValueError:
            pass

    def _normalize_limit_entry(self, event=None):
        try:
            val = max(0, int(self.limit_entry.get()))
        except ValueError:
            val = max(0, int(self.engine.click_limit))
        self.limit_entry.delete(0, "end")
        self.limit_entry.insert(0, str(val))
        self.engine.click_limit = val
        self._save_config()

    def _poll_event_queue(self):
        """Poll thread-safe event queue and process messages on the main Tkinter thread."""
        self._queue_poll_after_id = None
        if not self.winfo_exists():
            return
        try:
            self._drain_event_queue()
        finally:
            # Keep polling even if a handler raised, or engine/hotkey events would stop being processed
            if self.winfo_exists():
                self._queue_poll_after_id = self.after(20, self._poll_event_queue)

    def _drain_event_queue(self):
        """Drain all pending cross-thread events immediately."""
        try:
            while True:
                msg_type, data = self._event_queue.get_nowait()
                if msg_type == "click":
                    self._refresh_bezel_labels()
                elif msg_type == "state":
                    self._handle_state_change(data)
                elif msg_type == "countdown":
                    self._handle_countdown_update(data)
                elif msg_type == "error":
                    self._handle_engine_error(data)
                elif msg_type == "call":
                    data()
        except queue.Empty:
            pass

    def _on_state_change(self, is_running: bool):
        self._event_queue.put(("state", is_running))
        if threading.current_thread() == threading.main_thread():
            self._drain_event_queue()

    def _handle_state_change(self, is_running: bool):
        if not self.winfo_exists():
            return
        if is_running:
            self._input_error = False
            if not self._session_timer_after_id:
                self._session_timer_after_id = self.after(250, self._tick_session_timer)
        else:
            if self._session_timer_after_id:
                try:
                    self.after_cancel(self._session_timer_after_id)
                except Exception:
                    pass
                self._session_timer_after_id = None
            if self.engine.slow_presets and self.engine.get_effective_interval() >= 5.0:
                self.countdown_label.configure(text="Next: Ready")
                if not self.countdown_label.winfo_ismapped():
                    self.countdown_label.pack(side="right")
            else:
                self.countdown_label.pack_forget()

        self._refresh_status_summary()
        self._redraw_action_tray()

    def _on_click_update(self, total_clicks: int):
        self._event_queue.put(("click", total_clicks))
        if threading.current_thread() == threading.main_thread():
            self._drain_event_queue()

    def _on_countdown_update(self, remaining: float):
        self._event_queue.put(("countdown", remaining))
        if threading.current_thread() == threading.main_thread():
            self._drain_event_queue()

    def _handle_countdown_update(self, remaining: float):
        if not self.winfo_exists():
            return
        if self.engine.slow_presets and self.engine.get_effective_interval() >= 5.0:
            if self.engine.is_running and remaining > 0.0:
                if remaining >= 60.0:
                    mins = int(remaining // 60)
                    secs = int(remaining % 60)
                    self.countdown_label.configure(text=f"Next: {mins}m {secs:02d}s")
                else:
                    self.countdown_label.configure(text=f"Next: {remaining:.1f}s")
                if not self.countdown_label.winfo_ismapped():
                    self.countdown_label.pack(side="right")
            elif not self.engine.is_running:
                self.countdown_label.configure(text="Next: Ready")
                if not self.countdown_label.winfo_ismapped():
                    self.countdown_label.pack(side="right")
        else:
            self.countdown_label.pack_forget()

    def _reset_counter(self):
        self.engine.reset_counter()
        self._refresh_bezel_labels()

    # =========================================================================
    # Clicker Mode Controls
    # =========================================================================

    def _on_unit_change(self, unit: str):
        self.current_unit = unit
        try:
            val = float(self.speed_entry.get())
        except ValueError:
            val = 100.0

        if unit == "ms":
            ms = round(1000.0 / max(0.2, val))
            self.speed_entry.delete(0, "end")
            self.speed_entry.insert(0, str(ms))
            self.speed_slider.configure(from_=1, to=1000)
            self.speed_slider.set(min(1000, ms))
        else:
            cps = round(1000.0 / max(1.0, val), 1)
            self.speed_entry.delete(0, "end")
            self.speed_entry.insert(0, str(cps))
            self.speed_slider.configure(from_=0.5, to=100.0)
            self.speed_slider.set(min(100.0, cps))

        self._sync_engine_speed()
        self._save_config()

    def _on_slider_change(self, val: float):
        if self.current_unit == "ms":
            int_val = int(val)
            self.speed_entry.delete(0, "end")
            self.speed_entry.insert(0, str(int_val))
        else:
            float_val = round(val, 1)
            self.speed_entry.delete(0, "end")
            self.speed_entry.insert(0, str(float_val))
        self._sync_engine_speed()
        self._save_config()

    def _on_speed_entry_change(self, event=None):
        try:
            val = float(self.speed_entry.get())
            if self.current_unit == "ms":
                self.speed_slider.set(min(1000, max(1, val)))
            else:
                self.speed_slider.set(min(100, max(0.5, val)))
            self._sync_engine_speed()
            self._save_config()
        except ValueError:
            pass

    def _normalize_speed_entry(self, event=None):
        try:
            val = float(self.speed_entry.get())
            if not math.isfinite(val):
                raise ValueError("non-finite")
        except ValueError:
            ms = max(1, int(round(self.engine.interval_sec * 1000.0)))
            val = float(ms) if self.current_unit == "ms" else round(1000.0 / ms, 1)
        if self.current_unit == "ms":
            clean = str(max(1, min(3600000, int(round(val)))))
        else:
            clean = str(round(max(0.2, min(1000.0, val)), 1))
        self.speed_entry.delete(0, "end")
        self.speed_entry.insert(0, clean)
        self._on_speed_entry_change()

    def _sync_engine_speed(self):
        try:
            val = float(self.speed_entry.get())
            if self.current_unit == "ms":
                ms = max(1.0, val)
                self.engine.interval_sec = ms / 1000.0
                cps = 1000.0 / ms
                self.speed_info_label.configure(text=f"{cps:.1f} CPS")
            else:
                cps = max(0.2, val)
                self.engine.interval_sec = 1.0 / cps
                ms = (1.0 / cps) * 1000.0
                self.speed_info_label.configure(text=f"{ms:.0f} ms")
            self._refresh_status_summary()
        except ValueError:
            pass

    # =========================================================================
    # Options & Hotkey Rebinding (Keyboard + Mouse 4 / Mouse 5 / Mid Click)
    # =========================================================================

    def _on_mouse_button_change(self, btn: str):
        b = btn.lower()
        if b == "mid":
            b = "middle"
        if b == "middle" and self.hotkey_vk_code == VK_MID_CLICK:
            # Injected middle clicks would register as Mid Click hotkey presses and stop the clicker
            prev = self.engine.button.capitalize()
            self.btn_segmented.set("Mid" if prev == "Middle" else prev)
            self.hotkey_btn.configure(text="Bind in use")
            self.after(900, lambda: self.hotkey_btn.configure(text=f"{self.hotkey_listener.key_name} • Bind") if not self._capturing_hotkey else None)
            return
        self.engine.button = b
        self._save_config()

    def _on_click_type_change(self, click_type: str):
        self.engine.click_type = click_type.lower()
        self._save_config()

    def _on_target_key_change(self, key_name: str, vk_code: int):
        self.engine.target_key = key_name
        self.engine.target_key_vk = int(vk_code)
        self.target_key_btn.configure(text=f"{key_name} • Key")
        self._refresh_status_summary()
        self._save_config()

    def _begin_target_key_capture(self):
        if self._capturing_target_key:
            self._end_target_key_capture()
            return
        if self._capturing_hotkey:
            self._end_hotkey_capture()
        self._capturing_target_key = True
        self.hotkey_listener.set_suspended(True)
        self.target_key_btn.configure(text="Press key…")
        self._target_key_capture_binding = self.bind("<KeyPress>", self._capture_target_key, add="+")
        self.target_key_btn.focus_set()

    def _capture_target_key(self, event):
        if not self._capturing_target_key:
            return
        raw_name = event.keysym
        if raw_name == "Escape":
            self._end_target_key_capture()
            return "break"
        if raw_name in {"Win_L", "Win_R"}:
            return "break"
        vk_code = int(event.keycode)
        if raw_name in self._KEY_ALIASES:
            key_name = self._KEY_ALIASES[raw_name]
            vk_code = VK_MAP.get(key_name, vk_code)
        elif len(raw_name) == 1:
            key_name = raw_name.upper()
        else:
            key_name = raw_name

        if not 1 <= vk_code <= 255 or vk_code == 0x13:
            self.target_key_btn.configure(text="Invalid key")
            self.after(900, lambda: self.target_key_btn.configure(text="Press key…") if self._capturing_target_key else None)
            return "break"
        if vk_code == self.hotkey_vk_code:
            self.target_key_btn.configure(text="Used by Bind")
            self.after(900, lambda: self.target_key_btn.configure(text="Press key…") if self._capturing_target_key else None)
            return "break"

        self._end_target_key_capture()
        self._on_target_key_change(key_name, vk_code)
        return "break"

    def _end_target_key_capture(self):
        if self._capturing_target_key:
            self._capturing_target_key = False
            self.hotkey_listener.set_suspended(False)
            if self._target_key_capture_binding:
                self.unbind("<KeyPress>", self._target_key_capture_binding)
                self._target_key_capture_binding = None
            self.target_key_btn.configure(text=f"{self.engine.target_key} • Key")

    def _on_hotkey_change(self, key_name: str):
        self.hotkey_listener.set_key(key_name, self.hotkey_vk_code)
        self.hotkey_btn.configure(text=f"{key_name} • Bind")
        self._redraw_action_tray()
        self._save_config()

    def _begin_hotkey_capture(self):
        if self._capturing_hotkey:
            self._end_hotkey_capture()
            return
        if self._capturing_target_key:
            self._end_target_key_capture()
        self._capturing_hotkey = True
        self.hotkey_listener.set_suspended(True)
        self.hotkey_btn.configure(text="Press key…")
        self._hotkey_capture_binding = self.bind("<KeyPress>", self._capture_hotkey, add="+")
        self.hotkey_btn.focus_set()

        # Record initial mouse side/middle button states so only a fresh press triggers binding
        user32 = ctypes.windll.user32
        self._mouse_init_down = {
            vk: bool(user32.GetAsyncKeyState(vk) & 0x8000)
            for vk in (0x04, 0x05, 0x06)
        }
        self._mouse_capture_after_id = self.after(20, self._poll_mouse_capture)

    def _poll_mouse_capture(self):
        self._mouse_capture_after_id = None
        if not self._capturing_hotkey or not self.winfo_exists():
            return

        user32 = ctypes.windll.user32
        mouse_candidates = [
            (0x05, "Mouse 4"),
            (0x06, "Mouse 5"),
            (0x04, "Mid Click"),
        ]
        for vk, label in mouse_candidates:
            is_down = bool(user32.GetAsyncKeyState(vk) & 0x8000)
            if self._mouse_init_down.get(vk, False):
                if not is_down:
                    self._mouse_init_down[vk] = False
            elif is_down:
                if vk == VK_MID_CLICK and self.engine.button == "middle":
                    if self.active_mode == "clicker":
                        self.hotkey_btn.configure(text="Mid button!")
                        self.after(900, lambda: self.hotkey_btn.configure(text="Press key…") if self._capturing_hotkey else None)
                        self._mouse_init_down[vk] = True
                        break
                    self.engine.button = "left"
                    self.btn_segmented.set("Left")
                self.hotkey_vk_code = vk
                self._end_hotkey_capture()
                self._on_hotkey_change(label)
                return

        self._mouse_capture_after_id = self.after(20, self._poll_mouse_capture)

    def _capture_hotkey(self, event):
        if not self._capturing_hotkey:
            return
        raw_name = event.keysym
        if raw_name == "Escape":
            self._end_hotkey_capture()
            return "break"
        if raw_name in {"Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Win_L", "Win_R"}:
            return "break"
        vk_code = int(event.keycode)
        if raw_name in self._KEY_ALIASES:
            key_name = self._KEY_ALIASES[raw_name]
            vk_code = VK_MAP.get(key_name, vk_code)
        elif len(raw_name) == 1:
            key_name = raw_name.upper()
        else:
            key_name = raw_name

        if not 1 <= vk_code <= 255 or vk_code == 0x13:
            self.hotkey_btn.configure(text="Other key")
            self.after(900, lambda: self.hotkey_btn.configure(text="Press key…") if self._capturing_hotkey else None)
            return "break"
        if vk_code == self.engine.target_key_vk:
            if self.active_mode == "key_presser":
                self.hotkey_btn.configure(text="Target key!")
                self.after(900, lambda: self.hotkey_btn.configure(text="Press key…") if self._capturing_hotkey else None)
                return "break"
            else:
                alt_name, alt_vk = ("E", 0x45) if vk_code == 0x20 else ("Space", 0x20)
                self.engine.target_key = alt_name
                self.engine.target_key_vk = alt_vk
                self.target_key_btn.configure(text=f"{alt_name} • Key")

        self.hotkey_vk_code = vk_code
        self._end_hotkey_capture()
        self._on_hotkey_change(key_name)
        return "break"

    def _end_hotkey_capture(self):
        if self._capturing_hotkey:
            self._capturing_hotkey = False
            if self._mouse_capture_after_id:
                try:
                    self.after_cancel(self._mouse_capture_after_id)
                except Exception:
                    pass
                self._mouse_capture_after_id = None
            self.hotkey_listener.set_suspended(False)
            if self._hotkey_capture_binding:
                self.unbind("<KeyPress>", self._hotkey_capture_binding)
                self._hotkey_capture_binding = None
            self.hotkey_btn.configure(text=f"{self.hotkey_listener.key_name} • Bind")

    def _on_emergency_stop(self):
        # Stop directly from the hotkey thread so the emergency key works even if the UI is busy;
        # engine.stop() is thread-safe and reports state back through the event queue.
        self.engine.stop()

    def _on_engine_error(self, message: str):
        self._event_queue.put(("error", message))
        if threading.current_thread() == threading.main_thread():
            self._drain_event_queue()

    def _handle_engine_error(self, message: str):
        self._input_error = True
        if not self.winfo_exists():
            return
        self._refresh_status_summary()
        self.countdown_label.configure(text=f"Input error: {message[:40]}")

    def _toggle_pin_from_bezel(self):
        new_val = not bool(self.topmost_switch_var.get())
        self.topmost_switch_var.set(new_val)
        self.wm_attributes("-topmost", new_val)
        if self._taskbar_after_id:
            try:
                self.after_cancel(self._taskbar_after_id)
            except Exception:
                pass
        self._taskbar_after_id = self.after(10, self._enable_taskbar_icon)
        self._refresh_bezel_labels()
        self._save_config()

    def _on_jitter_toggle(self):
        is_jitter = bool(self.jitter_switch.get())
        self.engine.jitter_percent = 0.10 if is_jitter else 0.0
        self._save_config()

    def _apply_initial_ui_state(self, cfg: dict):
        is_top = bool(cfg.get("always_on_top", False))
        self.topmost_switch_var.set(is_top)
        self.wm_attributes("-topmost", is_top)

        # Restore saved window position if valid and on-screen (supports multi-monitor virtual desktop)
        wx = int(cfg.get("window_x", -1))
        wy = int(cfg.get("window_y", -1))
        if wx != -1 or wy != -1:
            self._window_pos = self._clamp_to_monitor(wx, wy, 360, 360)
        else:
            self._window_pos = None

        btn_val = cfg.get("mouse_button", "left").capitalize()
        if btn_val == "Middle":
            btn_val = "Mid"
        self.btn_segmented.set(btn_val)
        self.engine.button = cfg.get("mouse_button", "left")

        click_type = cfg.get("click_type", "single")
        self.type_segmented.set(click_type.capitalize())
        self.engine.click_type = click_type

        t_key = str(cfg.get("target_key", "Space"))
        self.engine.target_key = t_key
        self.engine.target_key_vk = int(cfg.get("target_key_vk", VK_MAP.get(t_key, 0x20)))
        self.target_key_btn.configure(text=f"{t_key} • Key")

        is_jitter = cfg.get("jitter", False)
        if is_jitter:
            self.jitter_switch.select()
            self.engine.jitter_percent = 0.10
        else:
            self.jitter_switch.deselect()
            self.engine.jitter_percent = 0.0

        unit = cfg.get("speed_unit", "ms")
        self.unit_segmented.set(unit)
        self.current_unit = unit
        if unit == "ms":
            ms = cfg.get("click_interval_ms", 100)
            self.speed_entry.delete(0, "end")
            self.speed_entry.insert(0, str(ms))
            self.speed_slider.configure(from_=1, to=1000)
            self.speed_slider.set(min(1000, max(1, ms)))
        else:
            cps = cfg.get("target_cps", 10.0)
            self.speed_entry.delete(0, "end")
            self.speed_entry.insert(0, str(cps))
            self.speed_slider.configure(from_=0.5, to=100.0)
            self.speed_slider.set(min(100.0, max(0.5, cps)))
        self._sync_engine_speed()

        hotkey = cfg.get("hotkey", "F6")
        self.hotkey_vk_code = int(cfg.get("hotkey_vk", VK_MAP.get(hotkey, 0x75)))
        self.hotkey_listener.set_key(hotkey, self.hotkey_vk_code)
        self.hotkey_btn.configure(text=f"{hotkey} • Bind")

        mode = cfg.get("active_mode", "clicker")
        if mode == "key_presser":
            self.mode_segmented.set("Key Presser")
            self._on_mode_change("Key Presser")
        else:
            self.mode_segmented.set("Clicker")
            self._on_mode_change("Clicker")

        trigger_mode = cfg.get("trigger_mode", "toggle")
        self.hotkey_listener.set_trigger_mode(trigger_mode)
        self.trigger_segmented.set("Toggle" if trigger_mode == "toggle" else "Hold Key")

        hold_ms = cfg.get("hold_duration_ms", 15)
        self.hold_entry.delete(0, "end")
        self.hold_entry.insert(0, str(hold_ms))
        self.engine.hold_duration_sec = hold_ms / 1000.0

        limit = cfg.get("click_limit", 0)
        self.limit_entry.delete(0, "end")
        self.limit_entry.insert(0, str(limit))
        self.engine.click_limit = limit

        panic = cfg.get("panic_corner", True)
        if panic:
            self.panic_switch.select()
        else:
            self.panic_switch.deselect()
        self.engine.panic_corner = panic

        snd = bool(cfg.get("sound_enabled", True))
        self.sound_enabled = snd
        if snd:
            self.sound_switch.select()
        else:
            self.sound_switch.deselect()

        self.engine.self_click_protection = bool(cfg.get("self_click_protection", True))

        lock_pos = bool(cfg.get("lock_cursor_pos", False))
        lx = int(cfg.get("locked_x", -1))
        ly = int(cfg.get("locked_y", -1))
        self.engine.locked_pos = (lx, ly) if (lx >= 0 and ly >= 0) else None
        self.engine.lock_cursor_pos = lock_pos
        if lock_pos:
            self.lock_pos_switch.select()
        else:
            self.lock_pos_switch.deselect()
        self._update_pick_pos_btn_label()

        central_scatter = cfg.get("central_scatter", False)
        if central_scatter:
            self.central_scatter_switch.select()
        else:
            self.central_scatter_switch.deselect()
        self.engine.central_scatter = central_scatter

        slow_presets = cfg.get("slow_presets", False)
        if slow_presets:
            self.slow_presets_switch.select()
        else:
            self.slow_presets_switch.deselect()
        self.engine.slow_presets = slow_presets

        preset_choice = cfg.get("slow_preset_choice", "fast")
        self.engine.slow_preset_choice = preset_choice
        ui_choice = "Very Slow" if preset_choice == "very_slow" else ("Slow" if preset_choice == "slow" else "Fast")
        self.main_slow_preset_segmented.set(ui_choice)
        self.settings_slow_preset_segmented.set(ui_choice)
        self._update_slow_preset_label(preset_choice)
        self._update_slow_presets_ui_visibility()

        self._on_state_change(False)
        self._refresh_bezel_labels()

    def _reset_all_settings(self):
        default_cfg = self.config_manager.reset()
        self.cfg = default_cfg
        self.sound_enabled = bool(default_cfg.get("sound_enabled", True))
        self._apply_initial_ui_state(default_cfg)
        self._save_config()

    def _collect_config(self) -> dict:
        try:
            speed_val = float(self.speed_entry.get())
        except (ValueError, AttributeError):
            speed_val = 100.0

        if self.current_unit == "ms":
            interval_ms = int(speed_val)
            target_cps = round(1000.0 / max(1.0, speed_val), 1)
        else:
            target_cps = speed_val
            interval_ms = int(1000.0 / max(0.1, speed_val))

        try:
            hold_ms = int(self.hold_entry.get())
        except (ValueError, AttributeError):
            hold_ms = 15

        try:
            limit = int(self.limit_entry.get())
        except (ValueError, AttributeError):
            limit = 0

        always_top = bool(self.topmost_switch_var.get())
        locked_pos = getattr(self.engine, "locked_pos", None) if hasattr(self, "engine") else None
        lx = int(locked_pos[0]) if locked_pos else -1
        ly = int(locked_pos[1]) if locked_pos else -1

        if self._window_pos is not None:
            wx, wy = int(self._window_pos[0]), int(self._window_pos[1])
        else:
            wx, wy = -1, -1

        return {
            "active_mode": getattr(self, "active_mode", "clicker"),
            "speed_unit": getattr(self, "current_unit", "ms"),
            "click_interval_ms": max(1, interval_ms),
            "target_cps": max(0.1, target_cps),
            "mouse_button": self.engine.button if hasattr(self, "engine") else "left",
            "click_type": self.engine.click_type if hasattr(self, "engine") else "single",
            "target_key": getattr(self.engine, "target_key", "Space") if hasattr(self, "engine") else "Space",
            "target_key_vk": int(getattr(self.engine, "target_key_vk", 0x20)) if hasattr(self, "engine") else 0x20,
            "jitter": (self.engine.jitter_percent > 0.0) if hasattr(self, "engine") else False,
            "hotkey": self.hotkey_listener.key_name if hasattr(self, "hotkey_listener") else "F6",
            "hotkey_vk": self.hotkey_vk_code if hasattr(self, "hotkey_vk_code") else 0x75,
            "trigger_mode": self.hotkey_listener.trigger_mode if hasattr(self, "hotkey_listener") else "toggle",
            "hold_duration_ms": max(1, hold_ms),
            "panic_corner": self.engine.panic_corner if hasattr(self, "engine") else True,
            "self_click_protection": getattr(self.engine, "self_click_protection", True) if hasattr(self, "engine") else True,
            "lock_cursor_pos": getattr(self.engine, "lock_cursor_pos", False) if hasattr(self, "engine") else False,
            "locked_x": lx,
            "locked_y": ly,
            "central_scatter": self.engine.central_scatter if hasattr(self, "engine") else False,
            "slow_presets": self.engine.slow_presets if hasattr(self, "engine") else False,
            "slow_preset_choice": getattr(self.engine, "slow_preset_choice", "fast") if hasattr(self, "engine") else "fast",
            "click_limit": max(0, limit),
            "always_on_top": always_top,
            "sound_enabled": getattr(self, "sound_enabled", True),
            "window_x": wx,
            "window_y": wy,
        }

    def _save_config(self):
        try:
            if self._save_after_id:
                self.after_cancel(self._save_after_id)
            self._save_after_id = self.after(350, self._write_config_now)
        except Exception:
            self._write_config_now()

    def _write_config_now(self):
        if self._save_after_id:
            try:
                self.after_cancel(self._save_after_id)
            except Exception:
                pass
            self._save_after_id = None
        try:
            cfg = self._collect_config()
            self.config_manager.save(cfg)
        except Exception:
            pass

    def destroy(self):
        self._write_config_now()
        self.engine.stop()
        self.hotkey_listener.stop()
        for aid in (
            self._save_after_id,
            self._tex_after_id,
            self._taskbar_after_id,
            self._taskbar_retry_after_id,
            self._fit_after_id,
            self._mouse_capture_after_id,
            self._pick_pos_after_id,
            self._session_timer_after_id,
            self._state_after_id,
            self._click_after_id,
            self._countdown_after_id,
            self._queue_poll_after_id,
        ):
            if aid:
                try:
                    self.after_cancel(aid)
                except Exception:
                    pass
        self._save_after_id = None
        self._tex_after_id = None
        self._taskbar_after_id = None
        self._taskbar_retry_after_id = None
        self._fit_after_id = None
        self._mouse_capture_after_id = None
        self._pick_pos_after_id = None
        self._session_timer_after_id = None
        self._state_after_id = None
        self._click_after_id = None
        self._countdown_after_id = None
        super().destroy()