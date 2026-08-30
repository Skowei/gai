"""
DuckDuckGo Web Search Tool
===========================
Enterprise web search - no API key required.
Uses ddgs library directly (lighter than langchain_community).
"""
import asyncio
import logging
from typing import Optional
from app.core.agent.tools.base import BaseTool
from app.core.agent.tools.registry import tool
from app.core.agent.tools.schemas import ToolResult, ToolStatus

logger = logging.getLogger(__name__)


@tool()
class DuckDuckGoTool(BaseTool):
    """Enterprise web search via DuckDuckGo - no API key required"""

    name = "web_search"
    description = "Search the internet for real-time information"
    version = "2.1.0"

    def __init__(self, config=None):
        super().__init__(config)
        self._engine = None

    def _get_engine(self):
        """Lazy engine init - graceful degradation if ddgs missing"""
        if self._engine is None:
            try:
                from ddgs import DDGS
                self._engine = DDGS()
            except ImportError:
                raise RuntimeError(
                    "ddgs package not installed. Run: pip install ddgs"
                )
        return self._engine

    def _search_sync(self, query: str, max_results: int):
        """Sync search - runs in executor"""
        engine = self._get_engine()
        raw = engine.text(query, max_results=max_results)
        results = []
        for item in raw:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("href", "") or item.get("url", ""),
                "snippet": item.get("body", "") or item.get("snippet", ""),
            })
        return results

    async def execute(self, query: str, max_results: int = 5, **kwargs) -> ToolResult:
        """Execute web search (non-blocking via executor)"""
        if not query or not query.strip():
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error="Search query cannot be empty"
            )

        try:
            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(
                None,
                self._search_sync,
                query.strip(),
                max(1, min(max_results, 10)),
            )

            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                data={
                    "query": query,
                    "results": results,
                    "total_found": len(results),
                }
            )
        except RuntimeError as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error=str(e)
            )
        except Exception as e:
            logger.error(f"[DuckDuckGo] Search failed: {e}", exc_info=True)
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error=f"Web search failed: {str(e)}"
            )

    def get_schema(self):
        schema = super().get_schema()
        schema["parameters"] = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query for internet research"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results (1-10)",
                    "default": 5
                }
            },
            "required": ["query"]
        }
        return schema
