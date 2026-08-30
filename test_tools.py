#!/usr/bin/env python3
"""Enterprise Tool System - Full Test Suite"""
import sys, os
os.chdir('/home/maciei/dev/ai')
sys.path.insert(0, '/home/maciei/dev/ai')

import types
for mod_name in ['app', 'app.core', 'app.core.agent', 'app.core.agent.tools']:
    m = types.ModuleType(mod_name)
    m.__path__ = [mod_name.replace('.', '/')]
    sys.modules[mod_name] = m

def test(name, fn):
    try:
        fn()
        print(f' [PASS] {name}')
        return True
    except Exception as e:
        print(f' [FAIL] {name}: {e}')
        import traceback; traceback.print_exc()
        return False

print('=' * 50)
print('Enterprise Tool System - Tests')
print('=' * 50)
from app.core.agent.tools.schemas import ToolResult, ToolStatus, ToolConfig
from app.core.agent.tools.base import BaseTool
from app.core.agent.tools.registry import ToolRegistry, registry, tool

# Schemas
assert ToolResult(tool_name='t', status=ToolStatus.SUCCESS).is_success
assert not ToolResult(tool_name='t', status=ToolStatus.ERROR, error='x').is_success
assert ToolConfig(timeout=60).timeout == 60
test('Schemas', lambda: None)

# BaseTool
class T(BaseTool):
    name='t'; description='d'; version='1'
    async def execute(self, **kw): pass
assert T().name == 't' and 'name' in T().get_schema()
test('BaseTool', lambda: None)

# Registry
assert ToolRegistry() is registry
test('Registry singleton', lambda: None)

# @tool decorator
@tool()
class RT(BaseTool):
    name='rt'; description='d'; version='1'
    async def execute(self, **kw): return ToolResult(tool_name=self.name, status=ToolStatus.SUCCESS)
assert 'rt' in registry.list_tools()
test('@tool decorator', lambda: None)

# DuckDuckGo
from app.core.agent.tools.web.duckduckgo import DuckDuckGoTool
assert DuckDuckGoTool().name == 'web_search'
assert 'query' in DuckDuckGoTool().get_schema()['parameters']['properties']
test('DuckDuckGoTool', lambda: None)

# Wikipedia
from app.core.agent.tools.web.wikipedia import WikipediaTool
assert WikipediaTool().name == 'wikipedia_search'
test('WikipediaTool', lambda: None)

# ArXiv
from app.core.agent.tools.web.arxiv import ArxivTool
assert ArxivTool().name == 'arxiv_search'
test('ArxivTool', lambda: None)

# PinchTab
from app.core.agent.tools.browser.pinchtab import PinchTabTool
pt = PinchTabTool()
assert pt.name == 'browser'
assert 'navigate' in pt.get_schema()['parameters']['properties']['action']['enum']
test('PinchTabTool', lambda: None)

# CodeExecutor
from app.core.agent.tools.code.executor import CodeExecutorTool
assert CodeExecutorTool().name == 'code_executor'
assert not CodeExecutorTool()._security_check('import os')['safe']
assert CodeExecutorTool()._security_check('print(1)')['safe']
test('CodeExecutorTool', lambda: None)

# MarkItDown
from app.core.agent.tools.documents.markitdown import MarkItDownTool
assert MarkItDownTool().name == 'document_converter'
assert '.pdf' in MarkItDownTool().SUPPORTED
test('MarkItDownTool', lambda: None)

# PDF
from app.core.agent.tools.documents.pdf import PDFTool
assert PDFTool().name == 'pdf_extractor'
test('PDFTool', lambda: None)

# FileEngine
from app.core.agent.tools.memory.file_engine import FileEngineTool
assert FileEngineTool().name == 'file_engine'
test('FileEngineTool', lambda: None)

# XML serialization
r = ToolResult(tool_name='w', status=ToolStatus.SUCCESS, data='result')
assert '<tool_result' in r.to_xml() and 'w' in r.to_xml()
test('XML serialization', lambda: None)

print('=' * 50)
print('ALL TESTS PASSED!')
