from __future__ import annotations

import os
import subprocess
import sys
import threading

from app.core.watchdog import process_alive, watch_parent


def test_process_alive():
    assert process_alive(os.getpid()) is True
    assert process_alive(0) is False
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    assert process_alive(proc.pid) is False


def test_watch_parent_calls_back_when_process_ends():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.5)"])
    gone = threading.Event()
    watch_parent(proc.pid, gone.set, interval=0.2)
    assert not gone.wait(0.1)
    proc.wait()
    assert gone.wait(3)
