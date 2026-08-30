"""
Enterprise AI Agent Tools
=========================
Tools auto-register via @tool decorator on import.

GRACEFUL DEGRADATION POLICY:
Each tool module is imported independently. A missing optional dependency
(e.g. arxiv, markitdown, pdfplumber) disables ONLY that single tool - it can
NEVER crash the application. This guarantees the API core always boots.
"""
import importlib
import logging

logger = logging.getLogger(__name__)

# --- Core (always required) ---
from app.core.agent.tools.registry import registry, ToolRegistry
from app.core.agent.tools.schemas import ToolResult, ToolStatus, ToolConfig
from app.core.agent.tools.base import BaseTool

# --- Tool modules: loaded independently, failures isolated ---
_TOOL_MODULES = [
    "app.core.agent.tools.web.duckduckgo",
    "app.core.agent.tools.web.arxiv",
    "app.core.agent.tools.web.wikipedia",
    "app.core.agent.tools.browser.pinchtab",
    "app.core.agent.tools.code.executor",
    "app.core.agent.tools.documents.markitdown",
    "app.core.agent.tools.documents.pdf",
    "app.core.agent.tools.memory.file_engine",
]

LOADED_TOOL_MODULES: list = []
FAILED_TOOL_MODULES: dict = {}

for _module_path in _TOOL_MODULES:
    try:
        importlib.import_module(_module_path)
        LOADED_TOOL_MODULES.append(_module_path)
    except ImportError as _e:
        # Missing optional dependency - degrade gracefully
        FAILED_TOOL_MODULES[_module_path] = str(_e)
        logger.warning(f"[Tools] Optional tool unavailable: {_module_path} ({_e})")
    except Exception as _e:
        # Unexpected error - still must not crash the app
        FAILED_TOOL_MODULES[_module_path] = str(_e)
        logger.error(f"[Tools] Tool failed to load: {_module_path} ({_e})", exc_info=True)

logger.info(
    f"[Tools] Registry ready: {len(registry.list_tools())} tools registered "
    f"({len(LOADED_TOOL_MODULES)}/{len(_TOOL_MODULES)} modules loaded)"
)

__all__ = [
    "registry",
    "ToolRegistry",
    "ToolResult",
    "ToolStatus",
    "ToolConfig",
    "BaseTool",
    "LOADED_TOOL_MODULES",
    "FAILED_TOOL_MODULES",
]
