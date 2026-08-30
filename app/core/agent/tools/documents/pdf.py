"""
PDF Extraction Tool
====================
Extract text and tables from PDF documents.
"""
import logging
from pathlib import Path
from app.core.agent.tools.base import BaseTool
from app.core.agent.tools.registry import tool
from app.core.agent.tools.schemas import ToolResult, ToolStatus

logger = logging.getLogger(__name__)


@tool()
class PDFTool(BaseTool):
    """Extract text content and tables from PDF documents"""
    
    name = "pdf_extractor"
    description = "Extract text content and tables from PDF documents"
    version = "1.0.0"
    
    async def execute(self, file_path: str, extract_tables: bool = False, **kwargs) -> ToolResult:
        """Extract content from PDF"""
        path = Path(file_path)
        if not path.exists() or path.suffix.lower() != '.pdf':
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error="Valid PDF file path required"
            )
        
        try:
            import pdfplumber
            
            text_content = []
            tables = []
            
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text_content.append(page.extract_text() or "")
                    
                    if extract_tables:
                        page_tables = page.extract_tables()
                        tables.extend(page_tables)
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                data={
                    "text": "\n\n".join(text_content),
                    "tables": tables if extract_tables else [],
                    "pages": len(text_content),
                    "file_path": file_path
                }
            )
            
        except ImportError:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error="pdfplumber not installed. Run: pip install pdfplumber"
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error=f"PDF extraction failed: {str(e)}"
            )
    
    def get_schema(self):
        schema = super().get_schema()
        schema["parameters"] = {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to PDF file"},
                "extract_tables": {"type": "boolean", "description": "Extract tables", "default": False}
            },
            "required": ["file_path"]
        }
        return schema
