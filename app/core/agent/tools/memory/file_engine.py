"""
File Engine Tool - Memory Operations
======================================
Save facts and preferences to long-term memory (L3).
"""
import logging
from typing import Optional, Any
from app.core.agent.tools.base import BaseTool
from app.core.agent.tools.registry import tool
from app.core.agent.tools.schemas import ToolResult, ToolStatus

logger = logging.getLogger(__name__)


@tool()
class FileEngineTool(BaseTool):
    """Save facts and preferences to long-term memory"""
    
    name = "file_engine"
    description = "Save new personal facts and preferences to memory (L3)"
    version = "2.0.0"
    
    def __init__(self, config=None):
        super().__init__(config)
        self._manager: Optional[Any] = None
        self._repository: Optional[Any] = None
    
    @property
    def repository(self):
        """Lazy initialization of memory repository (L3 writer)"""
        if self._repository is None:
            from app.memory.l2.client import UnifiedMemoryManager
            from app.memory.l2.repository import MemoryRepository
            self._manager = UnifiedMemoryManager()
            self._repository = MemoryRepository(self._manager)
        return self._repository
    
    async def execute(self, content: str, session_id: str = "default", **kwargs) -> ToolResult:
        """Save content to memory"""
        if not content or not content.strip():
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error="Content cannot be empty"
            )
        
        try:
            rel_path = f"knowledge_base/fact_{session_id}.md"
            await self.repository.save_to_local_notes_and_vector(
                rel_path=rel_path,
                content=content,
                metadata={"session_id": session_id, "memory_layer": "L3_Internal"}
            )
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                data={"saved_to": rel_path, "session_id": session_id}
            )
            
        except Exception as e:
            logger.error(f"[FileEngine] Save failed: {e}", exc_info=True)
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error=f"Failed to save: {str(e)}"
            )
    
    def get_schema(self):
        schema = super().get_schema()
        schema["parameters"] = {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Fact or preference to save"},
                "session_id": {"type": "string", "description": "Session identifier", "default": "default"}
            },
            "required": ["content"]
        }
        return schema
