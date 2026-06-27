"""
Tool Handler Registry — strategy pattern for tool dispatch.

Replaces the if/elif chains in tool_executor.py with a
pluggable registry. Each tool that needs special handling
registers its handler here.

Architecture:
  tool_executor calls → ToolRegistry.dispatch(name, args, agent)
                       → registered handler runs
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# Handler signature: (agent, function_name, arguments, **context) -> None
ToolHandler = Callable[..., None]

_registry: Dict[str, ToolHandler] = {}


def register(name: str, handler: ToolHandler) -> None:
    """Register a tool handler for special dispatch."""
    if name in _registry:
        logger.warning(f"ToolHandler '{name}' overwritten")
    _registry[name] = handler


def dispatch(name: str, agent, function_name: str, arguments: str, **context) -> bool:
    """Dispatch a tool call to its registered handler.
    
    Returns True if a handler was found and executed, False otherwise.
    """
    handler = _registry.get(name)
    if handler is None:
        return False
    try:
        handler(agent, function_name, arguments, **context)
        return True
    except Exception:
        logger.debug(f"ToolHandler '{name}' failed", exc_info=True)
        return False


def get_registered() -> list:
    """Return list of registered tool names."""
    return list(_registry.keys())


# ── Built-in registrations ──────────────────────────────────────────
# These are registered at import time. Additional tools can register
# themselves lazily via register().

def _register_builtins():
    """Register handlers for tools that need special executor treatment."""
    # Lazy imports to avoid circular dependencies at module level
    pass  # Builtins register themselves in their respective tool modules

# Register on import
_register_builtins()
