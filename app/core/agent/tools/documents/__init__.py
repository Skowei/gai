"""
Document Processing Tools
===========================
Universal document conversion and extraction.
GRACEFUL DEGRADATION: each tool loads independently.
"""
import logging

logger = logging.getLogger(__name__)

__all__ = []

try:
    from app.core.agent.tools.documents.markitdown import MarkItDownTool
    __all__.append("MarkItDownTool")
except ImportError as e:
    logger.warning(f"[DocTools] MarkItDownTool unavailable: {e}")

try:
    from app.core.agent.tools.documents.pdf import PDFTool
    __all__.append("PDFTool")
except ImportError as e:
    logger.warning(f"[DocTools] PDFTool unavailable: {e}")
