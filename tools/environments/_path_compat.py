"""Unified Windows/WSL path conversion utilities.

Provides four idempotent functions for path translation across
Windows, MSYS/Git Bash, and WSL environments, plus a single compiled
regex that every call-site shares.
"""

import os
import platform
import re

# ---------------------------------------------------------------------------
# Unified regex - the single source of truth for Windows drive-letter paths.
# Matches "C:\foo", "D:/bar", "c: baz" (the separator is optional).
# ---------------------------------------------------------------------------
_WIN_DRIVE_RE = re.compile(r'^([a-zA-Z]):[\/]?(.*)$')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def msys_to_windows(path: str) -> str:
    """Convert an MSYS / Git Bash POSIX path to native Windows form.

    /c/Users/x -> C:\\Users\\x
    /d          -> D:\

    *Idempotent* - calling it on an already-Windows path (or any path
    that does not match the MSYS pattern) returns it unchanged.
    No-ops immediately on non-empty *path* that does not start with
    /<single-letter>.
    """
    if not path:
        return path
    # Match leading "/<single letter>/" or exactly "/<letter>" (bare drive root).
    m = re.match(r'^/([a-zA-Z])(/.*)?$', path)
    if not m:
        return path
    drive = m.group(1).upper()
    tail = (m.group(2) or "").replace("/", "\\")
    return f"{drive}:{tail or chr(92)}"  # chr(92) == backslash


def windows_to_wsl(path: str) -> str:
    """Convert a Windows absolute path to WSL /mnt/<drive>/... form.

    D:\DAP -> /mnt/d/DAP
    C:/Users -> /mnt/c/Users

    *Idempotent* - calling it on an already-WSL path (or any path that
    does not match the Windows drive-letter pattern) returns it unchanged.
    """
    if not path:
        return path
    m = _WIN_DRIVE_RE.match(path)
    if not m:
        return path
    drive = m.group(1).lower()
    rest = m.group(2).replace("\\", "/")
    return f"/mnt/{drive}/{rest}" if rest else f"/mnt/{drive}"


def is_wsl_bash(bash_path: str) -> bool:
    """Return True if *bash_path* is the WSL launcher (not Git Bash / MSYS2).

    The WSL bash launcher on Windows 10/11 lives under
    %SystemRoot%\System32\bash.exe (or SysWOW64).
    Git Bash installs elsewhere - typically under Program Files,
    %LOCALAPPDATA%\Programs\Git, or Hermes's own portable Git.
    """
    if not bash_path:
        return False
    system_root = os.environ.get("SystemRoot", "") or r"C:\Windows"
    norm_bash = os.path.normpath(bash_path).lower()
    for subdir in ("system32", "syswow64"):
        if norm_bash.startswith(
            os.path.normpath(os.path.join(system_root, subdir)).lower()
        ):
            return True
    return False


def is_wsl() -> bool:
    """Return True if the Python process is running inside WSL.

    Detects WSL via the microsoft marker in platform.uname().release.
    Result is cached after the first call.
    """
    if not hasattr(is_wsl, '_cached'):
        try:
            is_wsl._cached = 'microsoft' in platform.release().lower()
        except Exception:
            is_wsl._cached = False
    return is_wsl._cached
