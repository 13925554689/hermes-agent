
"""
Path compatibility layer for Windows/WSL/Git Bash.

Unifies the 5 separate WSL path conversion implementations
that were scattered across base.py and local.py into one
module with three canonical functions.

All functions are IDEMPOTENT.
"""

from __future__ import annotations

import os
import re
import platform
from typing import Optional

_DRIVE_PATH_RE = re.compile(r'^([a-zA-Z]):[\\/]?(.*)$')

_IS_WSL: Optional[bool] = None
_IS_WINDOWS: bool = platform.system() == "Windows"


def is_wsl() -> bool:
    """Detect if running inside WSL via uname -r microsoft marker."""
    global _IS_WSL
    if _IS_WSL is not None:
        return _IS_WSL
    try:
        result = os.popen("uname -r 2>/dev/null").read()
        _IS_WSL = "microsoft" in result.lower()
    except Exception:
        _IS_WSL = False
    return _IS_WSL


def windows_to_wsl(path: str) -> str:
    """Convert Windows path to WSL (/mnt/drive/...). Idempotent."""
    if not path or not _IS_WINDOWS:
        return path
    if path.startswith("/mnt/") or path.startswith("/"):
        return path
    m = _DRIVE_PATH_RE.match(path)
    if not m:
        return path
    drive = m.group(1).lower()
    rest = m.group(2).replace("\\", "/")
    return f"/mnt/{drive}/{rest}" if rest else f"/mnt/{drive}"


def msys_to_windows(path: str) -> str:
    """Convert /mnt/... or /drive/... to Windows path. Idempotent."""
    if not path:
        return path
    if _DRIVE_PATH_RE.match(path):
        return path
    m = re.match(r'^/mnt/([a-zA-Z])(/.*)?$', path)
    if m:
        drive = m.group(1).upper()
        rest = (m.group(2) or "").replace("/", "\\")
        return f"{drive}:{rest}" if rest else f"{drive}:\\"
    m = re.match(r'^/([a-zA-Z])(/.*)?$', path)
    if m:
        drive = m.group(1).upper()
        rest = (m.group(2) or "").replace("/", "\\")
        return f"{drive}:{rest}" if rest else f"{drive}:\\"
    return path


def is_wsl_bash() -> bool:
    """Check if running in WSL bash (not Git Bash/MSYS2)."""
    return _IS_WINDOWS and is_wsl()


def normalize_for_shell(path: str) -> str:
    """Normalize path for current shell (WSL conversion if needed)."""
    if is_wsl():
        return windows_to_wsl(path)
    return path
