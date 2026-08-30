"""
Web Tools - Internet search and knowledge base tools
GRACEFUL DEGRADATION: each tool loads independently.
"""
import logging

logger = logging.getLogger(__name__)

__all__ = []

try:
    from app.core.agent.tools.web.duckduckgo import DuckDuckGoTool
    __all__.append("DuckDuckGoTool")
except ImportError as e:
    logger.warning(f"[WebTools] DuckDuckGoTool unavailable: {e}")

try:
    from app.core.agent.tools.web.arxiv import ArxivTool
    __all__.append("ArxivTool")
except ImportError as e:
    logger.warning(f"[WebTools] ArxivTool unavailable: {e}")

try:
    from app.core.agent.tools.web.wikipedia import WikipediaTool
    __all__.append("WikipediaTool")
except ImportError as e:
    logger.warning(f"[WebTools] WikipediaTool unavailable: {e}")
