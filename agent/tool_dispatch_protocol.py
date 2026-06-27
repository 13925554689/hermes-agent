"""
Tool Dispatch Protocol — decouples conversation_loop from model_tools.

Defines the interface that conversation_loop uses to dispatch tool calls
without importing model_tools directly. This breaks the bidirectional
coupling between the two modules.

Usage:
    # In conversation_loop.py:
    dispatcher: ToolDispatchProtocol = _ra().handle_function_call
    
    # The protocol ensures any dispatcher with the right signature works,
    # enabling testing with mocks and future transport backends.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol


class ToolDispatchProtocol(Protocol):
    """Protocol for dispatching tool calls from the conversation loop.
    
    Any object implementing this protocol can serve as the bridge between
    conversation_loop and model_tools, breaking the hard import dependency.
    """

    def __call__(
        self,
        agent: Any,
        function_name: str,
        arguments: str,
        assistant_message: Optional[Dict[str, Any]] = None,
        tool_call_id: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        task_id: Optional[str] = None,
        api_call_count: int = 0,
        call_index: int = 0,
        total_calls: int = 1,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Dispatch a single tool call.
        
        Args:
            agent: The AIAgent instance.
            function_name: Tool name (e.g. "terminal", "read_file").
            arguments: JSON string of tool arguments.
            assistant_message: Full assistant message containing tool_calls.
            tool_call_id: Unique ID for this tool call.
            messages: Conversation message list.
            task_id: Task identifier.
            api_call_count: Number of API calls made this turn.
            call_index: Index of this call within the batch.
            total_calls: Total calls in this batch.
            
        Returns:
            Dict with "output" key containing the tool result.
        """
        ...


# Type alias for clarity
ToolDispatcher = ToolDispatchProtocol
