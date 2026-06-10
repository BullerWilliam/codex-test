"""Multi-mouse overlay prototype for Windows.

This application uses the Windows Raw Input API to track individual physical
mice and draws one overlay cursor per mouse.  It intentionally avoids third
party runtime dependencies so it can be packaged with PyInstaller.

Important Windows limitation: ordinary user-mode Python programs cannot make
other applications natively understand several independent OS cursors.  The app
keeps the real Windows cursor synced to the selected "main" mouse so calls such
as GetCursorPos see that cursor.  Extra cursors are visual overlays and their
clicks/scrolls are injected as best-effort events at their overlay position.
A kernel HID filter driver or per-application/browser integration is required
for perfect multi-cursor hover semantics in every program.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import itertools
import math
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

if sys.platform != "win32":
    raise SystemExit("Multi Mouse Overlay requires Windows because it uses Raw Input APIs.")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
LRESULT = ctypes.c_ssize_t

# Explicit prototypes are important on 64-bit Windows because ctypes otherwise
# assumes int return values and can truncate HWND/HANDLE values.
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
user32.RegisterClassW.argtypes = [ctypes.c_void_p]
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL

WM_INPUT = 0x00FF
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
RIM_TYPEMOUSE = 0
RID_INPUT = 0x10000003
RIDEV_INPUTSINK = 0x00000100
RIDEV_NOLEGACY = 0x00000030
RIDEV_REMOVE = 0x00000001

RI_MOUSE_LEFT_BUTTON_DOWN = 0x0001
RI_MOUSE_LEFT_BUTTON_UP = 0x0002
RI_MOUSE_RIGHT_BUTTON_DOWN = 0x0004
RI_MOUSE_RIGHT_BUTTON_UP = 0x0008
RI_MOUSE_MIDDLE_BUTTON_DOWN = 0x0010
RI_MOUSE_MIDDLE_BUTTON_UP = 0x0020
RI_MOUSE_WHEEL = 0x0400

INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
GWL_EXSTYLE = -20
LWA_COLORKEY = 0x00000001

WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [
        ("dwType", wintypes.DWORD),
        ("dwSize", wintypes.DWORD),
        ("hDevice", wintypes.HANDLE),
        ("wParam", wintypes.WPARAM),
    ]


class RAWMOUSE_BUTTONS(ctypes.Structure):
    _fields_ = [("usButtonFlags", wintypes.USHORT), ("usButtonData", wintypes.USHORT)]


class RAWMOUSE_BUTTON_UNION(ctypes.Union):
    _fields_ = [("ulButtons", wintypes.ULONG), ("buttons", RAWMOUSE_BUTTONS)]


class RAWMOUSE(ctypes.Structure):
    _anonymous_ = ("button_union",)
    _fields_ = [
        ("usFlags", wintypes.USHORT),
        ("button_union", RAWMOUSE_BUTTON_UNION),
        ("ulRawButtons", wintypes.ULONG),
        ("lLastX", wintypes.LONG),
        ("lLastY", wintypes.LONG),
        ("ulExtraInformation", wintypes.ULONG),
    ]


class RAWINPUT_DATA(ctypes.Union):
    _fields_ = [("mouse", RAWMOUSE)]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("data", RAWINPUT_DATA)]


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", wintypes.USHORT),
        ("usUsage", wintypes.USHORT),
        ("dwFlags", wintypes.DWORD),
        ("hwndTarget", wintypes.HWND),
    ]


class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HCURSOR),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT]
user32.RegisterRawInputDevices.restype = wintypes.BOOL
user32.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPVOID, ctypes.POINTER(wintypes.UINT), wintypes.UINT]
user32.GetRawInputData.restype = wintypes.UINT
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = wintypes.BOOL
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = wintypes.LONG
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
user32.SetWindowLongW.restype = wintypes.LONG
user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF, wintypes.BYTE, wintypes.DWORD]
user32.SetLayeredWindowAttributes.restype = wintypes.BOOL

def _check_bool(ok: int, what: str) -> None:
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error(), what)


@dataclass
class CursorState:
    device: int
    color: str
    x: float
    y: float
    name: str
    last_seen: float = field(default_factory=time.time)
    left_down: bool = False
    right_down: bool = False


class RawMouseThread(threading.Thread):
    """Hidden Win32 message window that receives WM_INPUT mouse packets."""

    def __init__(self, on_raw_mouse: Callable[[int, int, int, int, int], None]) -> None:
        super().__init__(daemon=True)
        self.on_raw_mouse = on_raw_mouse
        self.hwnd: Optional[int] = None
        self._wndproc = WNDPROC(self._window_proc)
        self._ready = threading.Event()
        self._class_name = f"MultiMouseRawInputWindow-{id(self)}"

    def run(self) -> None:
        hinstance = kernel32.GetModuleHandleW(None)
        wndclass = WNDCLASS()
        wndclass.lpfnWndProc = self._wndproc
        wndclass.hInstance = hinstance
        wndclass.lpszClassName = self._class_name
        atom = user32.RegisterClassW(ctypes.byref(wndclass))
        _check_bool(atom, "RegisterClassW")

        hwnd = user32.CreateWindowExW(0, self._class_name, self._class_name, 0, 0, 0, 0, 0, None, None, hinstance, None)
        _check_bool(hwnd, "CreateWindowExW")
        self.hwnd = hwnd
        self._ready.set()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def wait_until_ready(self) -> int:
        self._ready.wait(timeout=5)
        if not self.hwnd:
            raise RuntimeError("Raw input window did not initialize")
        return self.hwnd

    def register(self, suppress_legacy: bool) -> None:
        hwnd = self.wait_until_ready()
        flags = RIDEV_INPUTSINK | (RIDEV_NOLEGACY if suppress_legacy else 0)
        rid = RAWINPUTDEVICE(0x01, 0x02, flags, hwnd)
        _check_bool(user32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(rid)), "RegisterRawInputDevices")

    def unregister_raw_input(self) -> None:
        rid = RAWINPUTDEVICE(0x01, 0x02, RIDEV_REMOVE, None)
        _check_bool(user32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(rid)), "RegisterRawInputDevices RIDEV_REMOVE")

    def close(self) -> None:
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    def _window_proc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if msg == WM_INPUT:
            self._handle_raw_input(lparam)
            return 0
        if msg in (WM_CLOSE, WM_DESTROY):
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _handle_raw_input(self, lparam: int) -> None:
        size = wintypes.UINT(0)
        header_size = ctypes.sizeof(RAWINPUTHEADER)
        user32.GetRawInputData(lparam, RID_INPUT, None, ctypes.byref(size), header_size)
        if not size.value:
            return
        buffer = ctypes.create_string_buffer(size.value)
        read = user32.GetRawInputData(lparam, RID_INPUT, buffer, ctypes.byref(size), header_size)
        if read == ctypes.c_uint(-1).value:
            return
        raw = ctypes.cast(buffer, ctypes.POINTER(RAWINPUT)).contents
        if raw.header.dwType != RIM_TYPEMOUSE:
            return
        mouse = raw.data.mouse
        self.on_raw_mouse(int(raw.header.hDevice or 0), int(mouse.lLastX), int(mouse.lLastY), int(mouse.usButtonFlags), int(mouse.usButtonData))


class MultiMouseApp:
    COLORS = ["#ff4d4d", "#4dff88", "#4da6ff", "#ffd24d", "#d24dff", "#4dfff3"]

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Multi Mouse Overlay")
        self.root.geometry("420x260")
        self.root.protocol("WM_DELETE_WINDOW", self.shutdown)

        self.enabled = False
        self.cursors: Dict[int, CursorState] = {}
        self.main_device: Optional[int] = None
        self._cursor_names = itertools.count(1)
        self._lock = threading.Lock()

        self.status = tk.StringVar(value="Disabled")
        self.device_text = tk.StringVar(value="No mice tracked yet.")
        self.suppress_legacy = tk.BooleanVar(value=True)
        self.inject_extra_clicks = tk.BooleanVar(value=True)

        self._build_gui()
        self._build_overlay()

        self.raw_thread = RawMouseThread(self._on_raw_mouse)
        self.raw_thread.start()
        self.root.after(16, self._tick)

    def _build_gui(self) -> None:
        tk.Label(self.root, text="Multi Mouse Overlay", font=("Segoe UI", 16, "bold")).pack(pady=(12, 4))
        tk.Label(self.root, textvariable=self.status, font=("Segoe UI", 11)).pack()
        tk.Button(self.root, text="Enable / Disable", command=self.toggle, width=22).pack(pady=10)
        tk.Checkbutton(self.root, text="Request no legacy mouse messages while enabled", variable=self.suppress_legacy).pack(anchor="w", padx=20)
        tk.Checkbutton(self.root, text="Best-effort inject clicks/scrolls for extra cursors", variable=self.inject_extra_clicks).pack(anchor="w", padx=20)
        tk.Label(self.root, textvariable=self.device_text, justify="left", anchor="w").pack(fill="both", expand=True, padx=20, pady=8)
        tk.Label(
            self.root,
            text="Middle-click any mouse to make it the main cursor reported by GetCursorPos.",
            wraplength=380,
            fg="#555555",
        ).pack(pady=(0, 10))

    def _build_overlay(self) -> None:
        self.overlay = tk.Toplevel(self.root)
        self.overlay.withdraw()
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        self.overlay.configure(bg="magenta")
        self.overlay.attributes("-transparentcolor", "magenta")
        self.canvas = tk.Canvas(self.overlay, bg="magenta", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.overlay.update_idletasks()
        hwnd = self.overlay.winfo_id()
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW)
        user32.SetLayeredWindowAttributes(hwnd, 0x00FF00FF, 0, LWA_COLORKEY)

    def toggle(self) -> None:
        if self.enabled:
            self.enabled = False
            try:
                self.raw_thread.unregister_raw_input()
            except OSError:
                pass
            self.status.set("Disabled")
            self.overlay.withdraw()
            return
        self.raw_thread.register(self.suppress_legacy.get())
        self.enabled = True
        self.status.set("Enabled: waiting for raw mouse input...")
        self._position_overlay()
        self.overlay.deiconify()

    def _position_overlay(self) -> None:
        width = self.root.winfo_screenwidth()
        height = self.root.winfo_screenheight()
        self.overlay.geometry(f"{width}x{height}+0+0")
        self.canvas.configure(width=width, height=height)

    def _on_raw_mouse(self, device: int, dx: int, dy: int, button_flags: int, button_data: int) -> None:
        if not self.enabled:
            return
        with self._lock:
            cursor = self._cursor_for_device(device)
            origin_x = user32.GetSystemMetrics(76)
            origin_y = user32.GetSystemMetrics(77)
            width = max(user32.GetSystemMetrics(78), 1)
            height = max(user32.GetSystemMetrics(79), 1)
            cursor.x = min(max(cursor.x + dx, origin_x), origin_x + width - 1)
            cursor.y = min(max(cursor.y + dy, origin_y), origin_y + height - 1)
            cursor.last_seen = time.time()
            if button_flags & RI_MOUSE_MIDDLE_BUTTON_DOWN:
                self.main_device = device
            self._update_buttons(cursor, button_flags)
            if self.inject_extra_clicks.get() and device != self.main_device:
                self._inject_buttons(cursor, button_flags, button_data)

    def _cursor_for_device(self, device: int) -> CursorState:
        if device not in self.cursors:
            index = len(self.cursors)
            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            self.cursors[device] = CursorState(
                device=device,
                color=self.COLORS[index % len(self.COLORS)],
                x=float(pt.x),
                y=float(pt.y),
                name=f"Cursor {next(self._cursor_names)}",
            )
            if self.main_device is None:
                self.main_device = device
        return self.cursors[device]

    def _update_buttons(self, cursor: CursorState, flags: int) -> None:
        if flags & RI_MOUSE_LEFT_BUTTON_DOWN:
            cursor.left_down = True
        if flags & RI_MOUSE_LEFT_BUTTON_UP:
            cursor.left_down = False
        if flags & RI_MOUSE_RIGHT_BUTTON_DOWN:
            cursor.right_down = True
        if flags & RI_MOUSE_RIGHT_BUTTON_UP:
            cursor.right_down = False

    def _inject_buttons(self, cursor: CursorState, flags: int, wheel_data: int) -> None:
        events = []
        if flags & RI_MOUSE_LEFT_BUTTON_DOWN:
            events.append((MOUSEEVENTF_LEFTDOWN, 0))
        if flags & RI_MOUSE_LEFT_BUTTON_UP:
            events.append((MOUSEEVENTF_LEFTUP, 0))
        if flags & RI_MOUSE_RIGHT_BUTTON_DOWN:
            events.append((MOUSEEVENTF_RIGHTDOWN, 0))
        if flags & RI_MOUSE_RIGHT_BUTTON_UP:
            events.append((MOUSEEVENTF_RIGHTUP, 0))
        if flags & RI_MOUSE_WHEEL:
            signed_wheel = ctypes.c_short(wheel_data).value
            events.append((MOUSEEVENTF_WHEEL, signed_wheel))
        for flag, data in events:
            self._send_mouse_input(cursor.x, cursor.y, flag, data)

    def _send_mouse_input(self, x: float, y: float, flag: int, data: int) -> None:
        width = max(user32.GetSystemMetrics(78), 1)
        height = max(user32.GetSystemMetrics(79), 1)
        origin_x = user32.GetSystemMetrics(76)
        origin_y = user32.GetSystemMetrics(77)
        abs_x = int((x - origin_x) * 65535 / max(width - 1, 1))
        abs_y = int((y - origin_y) * 65535 / max(height - 1, 1))
        inp = INPUT(INPUT_MOUSE, INPUT_UNION(mi=MOUSEINPUT(abs_x, abs_y, data, flag | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, 0, None)))
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

    def _sync_main_cursor(self) -> None:
        if self.main_device is None:
            return
        cursor = self.cursors.get(self.main_device)
        if cursor:
            user32.SetCursorPos(int(cursor.x), int(cursor.y))

    def _tick(self) -> None:
        if self.enabled:
            self._position_overlay()
            with self._lock:
                self._sync_main_cursor()
                self._draw_cursors()
                self._update_status_text()
        self.root.after(16, self._tick)

    def _draw_cursors(self) -> None:
        self.canvas.delete("all")
        for cursor in self.cursors.values():
            r = 9 if cursor.device == self.main_device else 7
            width = 3 if cursor.device == self.main_device else 2
            x, y = cursor.x, cursor.y
            self.canvas.create_line(x, y, x + 18, y + 26, fill=cursor.color, width=width)
            self.canvas.create_oval(x - r, y - r, x + r, y + r, outline=cursor.color, width=width)
            self.canvas.create_text(x + 28, y + 16, text=cursor.name + (" (main)" if cursor.device == self.main_device else ""), fill=cursor.color, anchor="w", font=("Segoe UI", 10, "bold"))

    def _update_status_text(self) -> None:
        count = len(self.cursors)
        self.status.set(f"Enabled: tracking {count} mouse{'es' if count != 1 else ''}")
        rows = []
        now = time.time()
        for cursor in self.cursors.values():
            age = now - cursor.last_seen
            rows.append(f"{cursor.name}: x={math.floor(cursor.x)} y={math.floor(cursor.y)} age={age:.1f}s" + (" MAIN" if cursor.device == self.main_device else ""))
        self.device_text.set("\n".join(rows) if rows else "Move a mouse to create its overlay cursor.")

    def shutdown(self) -> None:
        self.enabled = False
        try:
            self.raw_thread.unregister_raw_input()
        except OSError:
            pass
        self.raw_thread.close()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    MultiMouseApp().run()
