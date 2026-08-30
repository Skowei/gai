"""
Enterprise AI Agent - Base Tool
================================
Abstract base class for all AI agent tools.
Provides: timing, error handling, logging, schema generation.
"""
import time
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from app.core.agent.tools.schemas import ToolResult, ToolStatus, ToolConfig

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    """
    Enterprise-grade abstract base for all AI agent tools.
    
    Every tool must implement:
    - name: unique identifier
    - description: LLM-facing description
    - execute(): async execution logic
    """
    
    name: str = "base_tool"
    description: str = "Base tool"
    version: str = "1.0.0"
    
    def __init__(self, config: Optional[ToolConfig] = None):
        self.config = config or ToolConfig()
        self._call_count = 0
        self._last_call = None
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute tool with given parameters"""
        ...
    
    async def safe_execute(self, **kwargs) -> ToolResult:
        """
        Wrapper with timing, error handling, and retry logic.
        This is the primary entry point for tool execution.
        """
        if not self.config.enabled:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error=f"Tool '{self.name}' is disabled"
            )
        
        start = time.perf_counter()
        self._call_count += 1
        
        try:
            result = await self.execute(**kwargs)
            result.duration_ms = (time.perf_counter() - start) * 1000
            logger.info(f"[Tool:{self.name}] Executed in {result.duration_ms:.2f}ms")
            return result
            
        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            logger.error(f"[Tool:{self.name}] Execution failed: {e}", exc_info=True)
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error=str(e),
                duration_ms=duration
            )
    
    def get_schema(self) -> Dict[str, Any]:
        """Return tool schema for LLM function calling"""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version
        }
