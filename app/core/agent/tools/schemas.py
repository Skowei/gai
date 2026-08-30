"""
Enterprise AI Agent Tool Schemas
================================
Standardized result types for tool execution.
"""
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from enum import Enum
from datetime import datetime


class ToolStatus(str, Enum):
    """Tool execution status codes"""
    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"
    TIMEOUT = "timeout"


class ToolResult(BaseModel):
    """
    Standardized tool execution result.
    All tools return this unified format.
    """
    tool_name: str
    status: ToolStatus
    data: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @property
    def is_success(self) -> bool:
        return self.status == ToolStatus.SUCCESS

    def to_xml(self) -> str:
        """Convert to XML for LLM context injection"""
        if self.is_success:
            return f"""<tool_result name="{self.tool_name}" status="{self.status.value}">
{self.data}
</tool_result>"""
        else:
            return f"""<tool_result name="{self.tool_name}" status="error">
<error>{self.error}</error>
</tool_result>"""


class ToolConfig(BaseModel):
    """Tool configuration for enabling/disabling and timeouts"""
    enabled: bool = True
    timeout: int = 30
    max_retries: int = 0
    rate_limit: Optional[int] = None  # calls per minute
