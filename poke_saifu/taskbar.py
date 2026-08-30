"""Windows Taskbar Progress Integration.

Uses Windows COM interface ITaskbarList3 via ctypes to display progress
and status indicators directly on the application's taskbar icon.
"""

import sys
from typing import Optional


class TaskbarProgress:
    """Controls the Windows taskbar icon progress bar and states."""

    # TBPFLAG constants
    TBPF_NOPROGRESS = 0x00000000  # Progress bar is not displayed
    TBPF_INDETERMINATE = 0x00000001  # Progress bar cycles repeatedly
    TBPF_NORMAL = 0x00000002  # Normal green progress bar
    TBPF_ERROR = 0x00000004  # Red error progress bar
    TBPF_PAUSED = 0x00000008  # Yellow paused progress bar

    def __init__(self):
        self._taskbar = None
        self._set_progress_value_fn = None
        self._set_progress_state_fn = None

        if sys.platform != "win32":
            return

        try:
            import ctypes
            from ctypes import (
                POINTER,
                Structure,
                WINFUNCTYPE,
                byref,
                c_int,
                c_long,
                c_ulonglong,
                c_void_p,
                wintypes,
            )
            import uuid

            class GUID(Structure):
                _fields_ = [
                    ("Data1", wintypes.DWORD),
                    ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD),
                    ("Data4", wintypes.BYTE * 8),
                ]

                @classmethod
                def from_str(cls, guid_str: str):
                    u = uuid.UUID(guid_str)
                    fields = u.fields
                    data4 = (wintypes.BYTE * 8)(*u.bytes[8:])
                    return cls(fields[0], fields[1], fields[2], data4)

            ole32 = ctypes.oledll.ole32
            ole32.CoInitialize(None)

            clsid = GUID.from_str("{56FDF344-FD6D-11d0-958A-006097C9A090}")
            iid = GUID.from_str("{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}")

            taskbar_ptr = c_void_p()
            hr = ole32.CoCreateInstance(
                byref(clsid),
                None,
                1,  # CLSCTX_INPROC_SERVER
                byref(iid),
                byref(taskbar_ptr),
            )
            if hr != 0 or not taskbar_ptr:
                return

            self._taskbar = taskbar_ptr
            vtable_ptr = ctypes.cast(taskbar_ptr, POINTER(c_void_p)).contents
            vtable = ctypes.cast(vtable_ptr, POINTER(c_void_p))

            # HrInit (vtable index 3)
            hr_init_fn = WINFUNCTYPE(c_long, c_void_p)(vtable[3])
            hr_init_fn(self._taskbar)

            # SetProgressValue (vtable index 9)
            # HRESULT SetProgressValue(HWND hwnd, ULONGLONG ullCompleted, ULONGLONG ullTotal)
            self._set_progress_value_fn = WINFUNCTYPE(
                c_long, c_void_p, wintypes.HWND, c_ulonglong, c_ulonglong
            )(vtable[9])

            # SetProgressState (vtable index 10)
            # HRESULT SetProgressState(HWND hwnd, TBPFLAG tbpFlags)
            self._set_progress_state_fn = WINFUNCTYPE(
                c_long, c_void_p, wintypes.HWND, c_int
            )(vtable[10])
        except Exception:
            self._taskbar = None

    @property
    def is_available(self) -> bool:
        """Return True if taskbar progress integration is active."""
        return self._taskbar is not None

    def set_value(self, hwnd: Optional[int], completed: int, total: int = 1000) -> None:
        """Set numerical progress value (completed / total)."""
        if not self._taskbar or not hwnd or not self._set_progress_value_fn:
            return
        try:
            self._set_progress_value_fn(self._taskbar, hwnd, completed, total)
        except Exception:
            pass

    def set_state(self, hwnd: Optional[int], state: int) -> None:
        """Set taskbar progress state (NORMAL, PAUSED, ERROR, INDETERMINATE, NOPROGRESS)."""
        if not self._taskbar or not hwnd or not self._set_progress_state_fn:
            return
        try:
            self._set_progress_state_fn(self._taskbar, hwnd, state)
        except Exception:
            pass

    def set_progress(self, hwnd: Optional[int], val: float, paused: bool = False) -> None:
        """Set progress ratio from 0.0 to 1.0."""
        if not self._taskbar or not hwnd:
            return
        if val <= 0:
            self.set_state(hwnd, self.TBPF_NOPROGRESS)
        else:
            state = self.TBPF_PAUSED if paused else self.TBPF_NORMAL
            self.set_state(hwnd, state)
            self.set_value(hwnd, int(min(max(val, 0.0), 1.0) * 1000), 1000)

    def set_indeterminate(self, hwnd: Optional[int]) -> None:
        """Set progress to marquee / indeterminate animation."""
        self.set_state(hwnd, self.TBPF_INDETERMINATE)

    def set_paused(self, hwnd: Optional[int]) -> None:
        """Switch current progress bar to yellow paused state."""
        self.set_state(hwnd, self.TBPF_PAUSED)

    def set_resumed(self, hwnd: Optional[int]) -> None:
        """Switch current progress bar back to green normal state."""
        self.set_state(hwnd, self.TBPF_NORMAL)

    def set_error(self, hwnd: Optional[int]) -> None:
        """Set taskbar progress to red error state."""
        if not self._taskbar or not hwnd:
            return
        self.set_state(hwnd, self.TBPF_ERROR)
        self.set_value(hwnd, 1000, 1000)

    def clear(self, hwnd: Optional[int]) -> None:
        """Clear taskbar progress bar."""
        self.set_state(hwnd, self.TBPF_NOPROGRESS)
