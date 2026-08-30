"""
Wikipedia Knowledge Base Tool
==============================
Search Wikipedia for factual information.
"""
import logging
from app.core.agent.tools.base import BaseTool
from app.core.agent.tools.registry import tool
from app.core.agent.tools.schemas import ToolResult, ToolStatus

logger = logging.getLogger(__name__)


@tool()
class WikipediaTool(BaseTool):
    """Search Wikipedia knowledge base"""
    
    name = "wikipedia_search"
    description = "Search Wikipedia for factual information and knowledge"
    version = "1.0.0"
    
    async def execute(self, query: str, sentences: int = 3, **kwargs) -> ToolResult:
        """Search Wikipedia"""
        if not query or not query.strip():
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error="Search query cannot be empty"
            )
        
        try:
            import wikipedia
        except ImportError:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error="wikipedia package not installed. Run: pip install wikipedia"
            )

        try:
            summary = wikipedia.summary(query.strip(), sentences=sentences)
            page = wikipedia.page(query.strip())
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                data={
                    "title": page.title,
                    "summary": summary,
                    "url": page.url,
                    "query": query
                }
            )
            
        except wikipedia.exceptions.DisambiguationError as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.PARTIAL,
                data={"options": e.options[:5]},
                error=f"Disambiguation: be more specific. Did you mean: {e.options[:3]}?"
            )
        except wikipedia.exceptions.PageError:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error=f"No Wikipedia page found for '{query}'"
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error=f"Wikipedia search failed: {str(e)}"
            )
    
    def get_schema(self):
        schema = super().get_schema()
        schema["parameters"] = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query for Wikipedia"
                },
                "sentences": {
                    "type": "integer",
                    "description": "Number of summary sentences",
                    "default": 3
                }
            },
            "required": ["query"]
        }
        return schema
