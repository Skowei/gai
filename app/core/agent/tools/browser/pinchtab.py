"""
PinchTab Browser Automation Tool
=================================
Enterprise browser automation for web scraping, forms, and screenshots.

API Reference (pinchtab.com/docs):
- GET  /health                         -> server health check
- GET  /instances                      -> list browser instances
- POST /instances/start {"mode": "headless"} -> {"id": "inst_..."}
- POST /navigate        {"url": "..."} -> {"tabId", "title", "url"}
- GET  /snapshot?filter=interactive    -> {"nodes": [{"ref": "e1", "role": "button", "name": "..."}]}
- POST /action          {"kind": "click", "ref": "e1"} -> {"success": true}
- POST /action          {"kind": "fill", "ref": "e3", "text": "..."}
- GET  /text                           -> page text extraction
- GET  /screenshot                     -> PNG binary
"""
import httpx
import logging
import os
from typing import Optional
from app.core.agent.tools.base import BaseTool
from app.core.agent.tools.registry import tool
from app.core.agent.tools.schemas import ToolResult, ToolStatus, ToolConfig

logger = logging.getLogger(__name__)


@tool()
class PinchTabTool(BaseTool):
    """
    Enterprise browser automation via PinchTab.
    Supports: navigate, click, fill, extract, snapshot, screenshot
    """
    
    name = "browser"
    description = "Automate web browser: navigate, click elements, fill forms, extract text, take screenshots"
    version = "2.1.0"
    
    VALID_ACTIONS = ["navigate", "click", "fill", "extract", "snapshot", "screenshot"]
    
    def __init__(self, config: Optional[ToolConfig] = None):
        super().__init__(config)
        # Lazy config - read env var directly to avoid import-time dependency
        self.base_url = os.environ.get("PINCHTAB_URL", "http://pinchtab:9867")
        self.token = os.environ.get("PINCHTAB_TOKEN", "pinchtab-dev-token")
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def client(self) -> httpx.AsyncClient:
        """Lazy HTTP client initialization with Bearer auth"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.config.timeout,
                headers={"Authorization": f"Bearer {self.token}"}
            )
        return self._client
    
    async def execute(
        self, 
        action: str, 
        url: str = "", 
        ref: str = "", 
        text: str = "", 
        **kwargs
    ) -> ToolResult:
        """Execute browser automation action"""
        if action not in self.VALID_ACTIONS:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error=f"Invalid action '{action}'. Valid actions: {self.VALID_ACTIONS}"
            )
        
        # Parameter validation per action
        if action == "navigate" and not url.strip():
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error="Action 'navigate' requires 'url' parameter"
            )
        if action in ("click", "fill") and not ref.strip():
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error=f"Action '{action}' requires 'ref' parameter (get refs via 'snapshot' action first)"
            )
        if action == "fill" and not text:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error="Action 'fill' requires 'text' parameter"
            )
        
        if not await self._health_check():
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error=f"PinchTab server is not reachable at {self.base_url}"
            )
        
        try:
            instance_id = await self._get_or_create_instance()
            action_map = {
                "navigate": self._navigate,
                "click": self._click,
                "fill": self._fill,
                "extract": self._extract,
                "snapshot": self._snapshot,
                "screenshot": self._screenshot,
            }
            handler = action_map[action]
            result_data = await handler(url=url, ref=ref, text=text)
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                data={"action": action, "instance_id": instance_id, **result_data}
            )
        except httpx.TimeoutException:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.TIMEOUT,
                error=f"PinchTab request timed out after {self.config.timeout}s"
            )
        except Exception as e:
            logger.error(f"[PinchTab] Action '{action}' failed: {e}", exc_info=True)
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error=str(e)
            )
    
    async def _health_check(self) -> bool:
        """Check if PinchTab server is healthy"""
        try:
            resp = await self.client.get("/health")
            return resp.status_code == 200
        except Exception:
            return False
    
    async def _get_or_create_instance(self) -> str:
        """
        Get existing or create new browser instance.
        PinchTab uses always-on strategy by default, so server-level
        endpoints auto-route to the active instance. Instance creation
        is best-effort fallback.
        """
        try:
            resp = await self.client.get("/instances")
            data = resp.json()
            # API may return a bare list or {"instances": [...]} depending on version
            if isinstance(data, list):
                instances = data
            elif isinstance(data, dict):
                instances = data.get("instances", [])
            else:
                instances = []
            if instances:
                first = instances[0]
                if isinstance(first, dict):
                    return first.get("id", "active")
                return str(first)
            
            # Create new headless instance (response: {"id": "inst_...", ...})
            resp = await self.client.post("/instances/start", json={
                "mode": "headless"
            })
            body = resp.json()
            return body.get("id") or body.get("instanceId") or "active"
        except Exception as e:
            logger.warning(f"[PinchTab] Instance management failed, using server routing: {e}")
            return "active"
    
    async def _navigate(self, url: str = "", **kwargs) -> dict:
        """Navigate to URL - POST /navigate {"url": "..."}"""
        resp = await self.client.post("/navigate", json={"url": url})
        data = resp.json()
        return {
            "url": data.get("url", url),
            "title": data.get("title", ""),
            "status": "navigated"
        }
    
    async def _click(self, ref: str = "", **kwargs) -> dict:
        """Click element by ref - POST /action {"kind": "click", "ref": "e1"}"""
        resp = await self.client.post("/action", json={"kind": "click", "ref": ref})
        data = resp.json()
        if not data.get("success", False):
            raise RuntimeError(f"Click on '{ref}' failed: {data}")
        return {"ref": ref, "status": "clicked", "result": data.get("result", {})}
    
    async def _fill(self, ref: str = "", text: str = "", **kwargs) -> dict:
        """Fill form field - POST /action {"kind": "fill", "ref": "e3", "text": "..."}"""
        resp = await self.client.post("/action", json={"kind": "fill", "ref": ref, "text": text})
        data = resp.json()
        if not data.get("success", False):
            raise RuntimeError(f"Fill on '{ref}' failed: {data}")
        return {"ref": ref, "text_length": len(text), "status": "filled", "result": data.get("result", {})}
    
    async def _extract(self, **kwargs) -> dict:
        """Extract page text - GET /text"""
        resp = await self.client.get("/text")
        try:
            data = resp.json()
            text = data.get("text", "") if isinstance(data, dict) else str(data)
        except Exception:
            text = resp.text
        return {"text": text, "length": len(text), "status": "extracted"}
    
    async def _snapshot(self, **kwargs) -> dict:
        """Get interactive elements - GET /snapshot?filter=interactive -> {"nodes": [...]}"""
        resp = await self.client.get("/snapshot", params={"filter": "interactive"})
        data = resp.json()
        nodes = data.get("nodes", [])
        return {
            "elements": nodes,
            "element_count": len(nodes),
            "hint": "Use refs (e.g. 'e5') with click/fill actions",
            "status": "snapshot_taken"
        }
    
    async def _screenshot(self, **kwargs) -> dict:
        """Take screenshot - GET /screenshot (PNG binary)"""
        resp = await self.client.get("/screenshot")
        content_type = resp.headers.get("content-type", "")
        if "json" in content_type:
            return {"screenshot": resp.json(), "status": "screenshot_taken"}
        return {
            "size_bytes": len(resp.content),
            "content_type": content_type,
            "status": "screenshot_taken"
        }
    
    def get_schema(self):
        schema = super().get_schema()
        schema["parameters"] = {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["navigate", "click", "fill", "extract", "snapshot", "screenshot"],
                    "description": "Browser action to perform"
                },
                "url": {"type": "string", "description": "URL for navigate action"},
                "ref": {"type": "string", "description": "Element reference for click/fill actions"},
                "text": {"type": "string", "description": "Text content for fill action"}
            },
            "required": ["action"]
        }
        return schema

