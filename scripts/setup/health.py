from __future__ import annotations

import time
import urllib.error
import urllib.request


def wait_http_ok(url: str, timeout_seconds: float = 120.0, interval: float = 2.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if 200 <= getattr(resp, "status", 200) < 300:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(interval)
    return False
