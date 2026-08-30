"""
Python Code Executor Tool
==========================
Safe sandboxed execution of Python code.
"""
import ast
import logging
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr
from app.core.agent.tools.base import BaseTool
from app.core.agent.tools.registry import tool
from app.core.agent.tools.schemas import ToolResult, ToolStatus

logger = logging.getLogger(__name__)


@tool()
class CodeExecutorTool(BaseTool):
    """
    Safe Python code execution environment.
    Runs AI-generated code in sandboxed scope with security checks.
    """
    
    name = "code_executor"
    description = "Execute Python code safely for calculations, data analysis, and automation"
    version = "1.0.0"
    
    # Forbidden constructs for security
    FORBIDDEN = {'import', 'exec', 'eval', 'compile', '__import__', 'open'}
    
    # Safe builtins allowlist - what sandboxed code CAN use
    SAFE_BUILTINS = {
        'print': print, 'len': len, 'range': range, 'abs': abs,
        'min': min, 'max': max, 'sum': sum, 'sorted': sorted,
        'reversed': reversed, 'enumerate': enumerate, 'zip': zip,
        'list': list, 'dict': dict, 'set': set, 'tuple': tuple,
        'str': str, 'int': int, 'float': float, 'bool': bool,
        'round': round, 'isinstance': isinstance, 'map': map,
        'filter': filter, 'any': any, 'all': all, 'divmod': divmod,
    }
    
    async def execute(self, code: str, **kwargs) -> ToolResult:
        """Execute Python code safely"""
        if not code or not code.strip():
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error="Code cannot be empty"
            )
        
        # Security check
        security_result = self._security_check(code)
        if not security_result["safe"]:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error=f"Security violation: {security_result['reason']}"
            )
        
        try:
            # Capture output
            stdout_capture = StringIO()
            stderr_capture = StringIO()
            
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                # Execute in isolated namespace with safe builtins only
                sandbox_globals = {"__builtins__": dict(self.SAFE_BUILTINS)}
                local_vars = {}
                exec(compile(code, '<ai_generated>', 'exec'), sandbox_globals, local_vars)
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                data={
                    "stdout": stdout_capture.getvalue(),
                    "stderr": stderr_capture.getvalue(),
                    "variables": {k: str(v) for k, v in local_vars.items() if not k.startswith('_')}
                }
            )
            
        except SyntaxError as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error=f"Syntax error: {e.msg} (line {e.lineno})"
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error=f"Runtime error: {str(e)}"
            )
    
    def _security_check(self, code: str) -> dict:
        """Basic security validation - prevent dangerous operations"""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return {"safe": False, "reason": "Invalid Python syntax"}
        
        for node in ast.walk(tree):
            # Check for imports
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                return {"safe": False, "reason": "Import statements are not allowed"}
            
            # Check for forbidden builtins
            if isinstance(node, ast.Name) and node.id in self.FORBIDDEN:
                return {"safe": False, "reason": f"Forbidden: {node.id}"}
            
            # Check for forbidden function calls
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in self.FORBIDDEN:
                    return {"safe": False, "reason": f"Forbidden function: {node.func.id}"}
        
        return {"safe": True}
    
    def get_schema(self):
        schema = super().get_schema()
        schema["parameters"] = {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute (no imports allowed)"
                }
            },
            "required": ["code"]
        }
        return schema
