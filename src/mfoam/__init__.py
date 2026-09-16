from __future__ import annotations

import os
import sys

os.environ.setdefault("PYTHONUTF8", "1")

if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
