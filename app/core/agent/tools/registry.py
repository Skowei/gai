"""
Enterprise AI Agent - Tool Registry
====================================
Central registry for all agent tools.
Supports decorator-based registration with singleton pattern.
"""
import logging
from typing import Dict, List, Optional, Type
from app.core.agent.tools.base import BaseTool
from app.core.agent.tools.schemas import ToolConfig

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Central registry for all agent tools.
    Uses singleton pattern for global access.
    """
    
    _instance: Optional['ToolRegistry'] = None
    _tools: Dict[str, BaseTool] = {}
    _tool_classes: Dict[str, Type[BaseTool]] = {}
    
    def __new__(cls) -> 'ToolRegistry':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
            cls._instance._tool_classes = {}
        return cls._instance
    
    def register(self, tool_class: Type[BaseTool], config: Optional[ToolConfig] = None) -> Type[BaseTool]:
        """Register a tool class and create instance"""
        instance = tool_class(config=config)
        self._tools[instance.name] = instance
        self._tool_classes[instance.name] = tool_class
        logger.info(f"[Registry] Registered tool: {instance.name} v{instance.version}")
        return tool_class
    
    def get(self, name: str) -> Optional[BaseTool]:
        """Get tool by name"""
        return self._tools.get(name)
    
    def list_tools(self) -> List[str]:
        """List all registered tool names"""
        return list(self._tools.keys())
    
    def get_all(self) -> Dict[str, BaseTool]:
        """Get all registered tools"""
        return self._tools.copy()
    
    def get_schemas(self) -> List[Dict]:
        """Get schemas for all registered tools"""
        return [tool.get_schema() for tool in self._tools.values()]
    
    async def execute(self, name: str, **kwargs) -> 'ToolResult':
        """Execute tool by name with given parameters"""
        from app.core.agent.tools.schemas import ToolResult, ToolStatus
        
        tool = self.get(name)
        if not tool:
            return ToolResult(
                tool_name=name,
                status=ToolStatus.ERROR,
                error=f"Tool '{name}' not found in registry. Available: {self.list_tools()}"
            )
        return await tool.safe_execute(**kwargs)


def tool(config: Optional[ToolConfig] = None):
    """
    Decorator for auto-registering tools.
    
    Usage:
        @tool()
        class MyTool(BaseTool):
            ...
    """
    def decorator(cls: Type[BaseTool]) -> Type[BaseTool]:
        registry = ToolRegistry()
        registry.register(cls, config)
        return cls
    return decorator


# Global registry instance
registry = ToolRegistry()
