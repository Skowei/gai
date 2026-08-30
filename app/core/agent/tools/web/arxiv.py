"""
ArXiv Academic Papers Tool
===========================
Search academic papers and research articles.
"""
import logging
from app.core.agent.tools.base import BaseTool
from app.core.agent.tools.registry import tool
from app.core.agent.tools.schemas import ToolResult, ToolStatus

logger = logging.getLogger(__name__)


@tool()
class ArxivTool(BaseTool):
    """Search academic papers in arXiv database"""
    
    name = "arxiv_search"
    description = "Search for academic papers and research articles in arXiv"
    version = "1.0.0"
    
    async def execute(self, query: str, max_results: int = 3, **kwargs) -> ToolResult:
        """Search arXiv for academic papers"""
        if not query or not query.strip():
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error="Search query cannot be empty"
            )
        
        try:
            import arxiv
        except ImportError:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error="arxiv package not installed. Run: pip install arxiv"
            )

        try:
            search = arxiv.Search(
                query=query.strip(),
                max_results=min(max_results, 10),
                sort_by=arxiv.SortCriterion.Relevance
            )
            
            # arxiv>=2.2 removed Search.results(); canonical API is Client.results()
            client = arxiv.Client()
            
            papers = []
            for paper in client.results(search):
                papers.append({
                    "title": paper.title,
                    "summary": paper.summary[:500] if paper.summary else "",
                    "url": paper.pdf_url,
                    "authors": [a.name for a in paper.authors[:3]],
                    "published": paper.published.isoformat() if paper.published else None
                })
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                data={
                    "query": query,
                    "papers": papers,
                    "total_found": len(papers)
                }
            )
            
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error=f"arXiv search failed: {str(e)}"
            )
    
    def get_schema(self):
        schema = super().get_schema()
        schema["parameters"] = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query for academic papers"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results (1-10)",
                    "default": 3
                }
            },
            "required": ["query"]
        }
        return schema
