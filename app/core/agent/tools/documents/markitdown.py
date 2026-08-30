"""
MarkItDown Universal Document Converter
========================================
Convert documents (Word, Excel, PDF, PPT, images) to Markdown.
"""
import logging
from pathlib import Path
from app.core.agent.tools.base import BaseTool
from app.core.agent.tools.registry import tool
from app.core.agent.tools.schemas import ToolResult, ToolStatus

logger = logging.getLogger(__name__)


@tool()
class MarkItDownTool(BaseTool):
    """
    Universal document converter.
    Converts Word, Excel, PDF, PPT, images to Markdown format.
    """
    
    name = "document_converter"
    description = "Convert documents (Word, Excel, PDF, PPT, images) to Markdown format"
    version = "1.0.0"
    
    SUPPORTED = {'.pdf', '.docx', '.xlsx', '.pptx', '.html', '.csv', '.png', '.jpg', '.jpeg', '.md', '.txt', '.json', '.xml'}
    
    def __init__(self, config=None):
        super().__init__(config)
        try:
            from markitdown import MarkItDown
            self._converter = MarkItDown()
        except ImportError:
            logger.error("markitdown not installed. Run: pip install markitdown")
            self._converter = None
    
    async def execute(self, file_path: str, **kwargs) -> ToolResult:
        """Convert document to Markdown"""
        if self._converter is None:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error="MarkItDown not available. Install: pip install markitdown"
            )
        
        path = Path(file_path)
        if not path.exists():
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error=f"File not found: {file_path}"
            )
        
        if path.suffix.lower() not in self.SUPPORTED:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error=f"Unsupported format: {path.suffix}. Supported: {self.SUPPORTED}"
            )
        
        try:
            result = self._converter.convert(file_path)
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                data={
                    "original_path": file_path,
                    "file_type": path.suffix.lower(),
                    "markdown": result.text_content,
                    "length": len(result.text_content)
                }
            )
            
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error=f"Conversion failed: {str(e)}"
            )
    
    def get_schema(self):
        schema = super().get_schema()
        schema["parameters"] = {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the document file"
                }
            },
            "required": ["file_path"]
        }
        return schema
