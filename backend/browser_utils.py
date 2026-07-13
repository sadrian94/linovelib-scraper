"""Browser utility - auto-detect Edge or Chrome for DrissionPage."""

from __future__ import annotations

import shutil
import socket
from pathlib import Path

from DrissionPage import Chromium, ChromiumOptions

_EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def _find_browser(candidates: list[str]) -> str | None:
    for path in candidates:
        if Path(path).exists():
            return path
    return None


def _find_free_port(start: int = 9222) -> int:
    """Find a free port starting from the given port number."""
    port = start
    while port < start + 100:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
        port += 1
    return start


def find_browser_path() -> str:
    """Auto-detect Edge or Chrome browser path, or use PATH fallback."""
    path = _find_browser(_EDGE_PATHS)
    if path:
        return path
    path = _find_browser(_CHROME_PATHS)
    if path:
        return path
    for name in ("msedge", "chrome", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    return r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def create_browser() -> Chromium:
    """Create a DrissionPage Chromium browser with auto-detected path and port."""
    browser_path = find_browser_path()
    port = _find_free_port(9222)

    # Read headless configuration from DB
    headless = True
    db_path = Path(__file__).resolve().parent.parent / "bili-config.db"
    conn = None
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT VALUE FROM config WHERE KEY = 'headless_mode'")
            row = cursor.fetchone()
            if row:
                headless = row[0].strip().lower() == 'true'
        finally:
            conn.close()
    except Exception:
        pass

    co = ChromiumOptions()
    co.set_browser_path(browser_path)
    co.set_argument("--no-first-run")
    co.set_argument("--no-default-browser-check")
    co.set_argument("--disable-features=TranslateUI")
    co.set_argument("--disable-background-networking")
    if headless:
        if hasattr(co, "set_headless"):
            co.set_headless(True)
        else:
            co.headless(True)
    co.set_local_port(port)

    print(f"使用浏览器: {browser_path} (Headless: {headless})")
    print(f"调试端口: {port}")
    return Chromium(co)
