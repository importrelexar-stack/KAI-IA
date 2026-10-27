"""Vigila el proceso de la app de escritorio: si desaparece (cierre abrupto, "Finalizar tarea"),
KAI Core se detiene solo para no quedar como proceso huérfano."""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from collections.abc import Callable

log = logging.getLogger(__name__)


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def watch_parent(pid: int, on_gone: Callable[[], None], interval: float = 2.0) -> threading.Thread:
    def loop() -> None:
        while True:
            time.sleep(interval)
            if not process_alive(pid):
                log.warning("La app de escritorio (pid %s) ya no existe: KAI Core se detiene", pid)
                on_gone()
                return

    t = threading.Thread(target=loop, name="kai-parent-watchdog", daemon=True)
    t.start()
    return t
