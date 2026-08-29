from typing import List, Dict, Any, Optional, Annotated
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage

def append_entry(existing: List[Dict[str, Any]], new_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Guarantees thread-safe appending of tool execution results to the state payload."""
    if not existing:
        return new_entries if new_entries else []
    if not new_entries:
        return existing
    return existing + new_entries

def append_messages(existing: List[BaseMessage], new_messages: List[BaseMessage]) -> List[BaseMessage]:
    """Correct message history reducer configuration required by LangGraph channels."""
    if not existing:
        return new_messages if new_messages else []
    if not new_messages:
        return existing
    return existing + new_messages


class AgentState(BaseModel):
    """
    Thread-safe unified state architecture for the Enterprise AI Ecosystem.
    Utilizes LangGraph Annotated state channels to preserve complete message execution histories.
    """
    messages: Annotated[List[BaseMessage], append_messages] = Field(default_factory=list)
    
    # --- MEMORY LAYERS L1-L4 ---
    memory_context: str = Field(default="", description="Semantic context payload retrieved from L2/L4 Postgres RAG")
    session_id: str = Field(default="default_session", description="Unique identifier for the active chat session")
    
    # --- COGNITIVE CORE PROCESSOR & ROUTING ---
    is_reasoning: bool = Field(default=False, description="Flag indicating if the DeepSeek L0 core is active")
    reason_response: str = Field(default="", description="Raw cognitive processing stream from the <think> block")
    next_step: Optional[str] = Field(default=None, description="Active execution target selected by the cognitive router")
    target_role: Optional[str] = Field(default=None, description="Target model deployment role defined in models.yaml")
    search_query: str = Field(default="", description="Pruned, optimized search query generated dynamically by the LLM core")

    # --- MCP TOOLS & LIVE NETWORK EXTENSIONS ---
    # We strictly preserve your native append_entry reducer channel here
    tool_responses: Annotated[List[Dict[str, Any]], append_entry] = Field(default_factory=list)
    
    tool_summary: str = Field(default="", description="Synthetic textual summary of all executed tool outputs combined")
    final_response: str = ""
    system_instructions: str = Field(default="You are an autonomous AI core.", description="Active top-level system directives")

    class Config:
        arbitrary_types_allowed = True
