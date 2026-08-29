"""
Shared utilities for agent nodes.
Contains common helper functions to avoid code duplication.
"""
from typing import Any, List
from app.core.agent.state import AgentState


def get_last_user_message(state: AgentState) -> str:
    """
    Safely extracts the last user message from the agent state.
    Handles both Pydantic model and dict representations.
    Supports string messages, dict messages, and objects with .content attribute.
    """
    messages = getattr(state, "messages", []) if not isinstance(state, dict) else state.get("messages", [])
    if not messages:
        return ""
    
    last_message = messages[-1]
    
    # Handle string messages
    if isinstance(last_message, str):
        return last_message
    
    # Handle dict messages
    if isinstance(last_message, dict):
        return str(last_message.get("content", ""))
    
    # Handle objects with .content attribute (HumanMessage, AIMessage, etc.)
    if hasattr(last_message, "content"):
        return str(last_message.content)
    
    return str(last_message)


def safe_get_attr(state: Any, attr_name: str, default: str = "") -> str:
    """
    Safely gets an attribute from state, handling both Pydantic models and dicts.
    """
    if isinstance(state, dict):
        return state.get(attr_name, default)
    return getattr(state, attr_name, default)