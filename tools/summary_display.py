"""Live display hook for web-extract summarization streams.

When ``web_extract`` summarizes a long page, the summarizer LLM call can take
many seconds with no visible activity. Front-ends (currently the interactive
CLI) can register a callback here to mirror the summary tokens into a live
box — the same UX as streaming reasoning blocks.

Design constraints:
- Zero coupling: ``tools/web_tools.py`` only calls module functions here; if
  no front-end registered a callback (gateway, cron, subagents, tests) every
  call is a cheap no-op and the summarizer runs exactly as before.
- One stream at a time: ``web_extract`` summarizes multiple pages in
  parallel. Only the first task to acquire the display slot streams to the
  terminal; the others run silently. This avoids interleaved boxes.

Callback protocol::

    callback(event: str, **kwargs)

    event == "start": kwargs = {"url": str, "title": str}
    event == "delta": kwargs = {"text": str}
    event == "end":   kwargs = {"char_count": int, "ok": bool}

The callback must never raise — but we guard anyway.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_callback: Optional[Callable] = None
_slot_lock = threading.Lock()
_slot_holder: Optional[object] = None


def set_summary_stream_callback(callback: Optional[Callable]) -> None:
    """Register (or clear, with None) the live summary display callback."""
    global _callback
    _callback = callback


def get_summary_stream_callback() -> Optional[Callable]:
    """Return the registered callback, or None."""
    return _callback


def try_acquire_stream_slot(token: object) -> bool:
    """Try to claim the single live-display slot for ``token``.

    Returns True when the caller may stream to the display. Callers MUST
    call :func:`release_stream_slot` with the same token when done.
    Returns False immediately (non-blocking) when another stream owns the
    slot or no callback is registered.
    """
    global _slot_holder
    if _callback is None:
        return False
    with _slot_lock:
        if _slot_holder is None:
            _slot_holder = token
            return True
        return False


def release_stream_slot(token: object) -> None:
    """Release the live-display slot if ``token`` owns it."""
    global _slot_holder
    with _slot_lock:
        if _slot_holder is token:
            _slot_holder = None


def emit(event: str, **kwargs) -> None:
    """Invoke the registered callback, swallowing any error."""
    cb = _callback
    if cb is None:
        return
    try:
        cb(event, **kwargs)
    except Exception:
        logger.debug("summary display callback failed for event %s", event, exc_info=True)
