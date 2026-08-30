from typing import List, Dict, Any, Optional, Annotated
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage


def append_entry(existing: List[Dict[str, Any]], new_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Thread-safe appending of tool execution results."""
    if not existing:
        return new_entries if new_entries else []
    if not new_entries:
        return existing
    return existing + new_entries


def append_messages(existing: List[BaseMessage], new_messages: List[BaseMessage]) -> List[BaseMessage]:
    """Correct message history reducer for LangGraph channels."""
    if not existing:
        return new_messages if new_messages else []
    if not new_messages:
        return existing
    return existing + new_messages


class AgentState(BaseModel):
    """Enterprise Agent State - unified state architecture."""
    messages: Annotated[List[BaseMessage], append_messages] = Field(default_factory=list)
    
    # --- MEMORY LAYERS L1-L4 ---
    memory_context: str = Field(default='', description='Semantic context from L2/L4 RAG')
    session_id: str = Field(default='default_session', description='Unique session identifier')
    
    # --- COGNITIVE CORE ---
    is_reasoning: bool = Field(default=False, description='DeepSeek L0 core active flag')
    reason_response: str = Field(default='', description='Raw cognitive processing stream')
    next_step: Optional[str] = Field(default=None, description='Execution target from router')
    target_role: Optional[str] = Field(default=None, description='Model role from models.yaml')
    search_query: str = Field(default='', description='Optimized search query')
    
    # --- TOOL PARAMETERS ---
    code: str = Field(default='', description='Python code for execution')
    browser_url: str = Field(default='', description='Target URL for browser automation')
    browser_action: str = Field(default='', description='Browser action type')
    browser_ref: str = Field(default='', description='Element reference')
    browser_text: str = Field(default='', description='Text for fill actions')
    
    # --- TOOL RESULTS ---
    tool_responses: Annotated[List[Dict[str, Any]], append_entry] = Field(default_factory=list)
    tool_summary: str = Field(default='', description='Combined tool outputs')
    final_response: str = ''
    system_instructions: str = Field(default='You are an autonomous AI core.')

    class Config:
        arbitrary_types_allowed = True
