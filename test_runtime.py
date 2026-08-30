#!/usr/bin/env python3
"""Runtime tests - actual tool execution via real package __init__"""
import sys, os, asyncio
os.chdir('/home/maciei/dev/ai')
sys.path.insert(0, '/home/maciei/dev/ai')

# Mock ONLY the heavy app package chain (config/redis/etc.),
# let the real tools package __init__.py run (graceful degradation test)
import types
for mod_name in ['app', 'app.core', 'app.core.agent']:
    m = types.ModuleType(mod_name)
    m.__path__ = [mod_name.replace('.', '/')]
    sys.modules[mod_name] = m

from app.core.agent.tools import registry, LOADED_TOOL_MODULES, FAILED_TOOL_MODULES

async def main():
    print('=' * 55)
    print('RUNTIME TESTS - actual tool execution')
    print('=' * 55)

    print(f'\n[0] Tool loading report')
    print(f'    loaded: {len(LOADED_TOOL_MODULES)}, failed: {len(FAILED_TOOL_MODULES)}')
    for mod, err in FAILED_TOOL_MODULES.items():
        print(f'    SKIPPED {mod.split(".")[-1]}: {err[:60]}')
    available = registry.list_tools()
    print(f'    registered tools: {available}')

    results = []

    # 1. CodeExecutor - safe code
    if 'code_executor' in available:
        print('\n[1] CodeExecutor - safe code')
        result = await registry.execute('code_executor', code="result = 2 + 2\nprint(f'Answer: {result}')")
        print(f'    status={result.status.value}, duration={result.duration_ms:.1f}ms')
        print(f'    stdout={result.data.get("stdout", "").strip() if result.data else None}')
        ok = result.status.value == 'success' and result.data and '4' in result.data.get('stdout', '')
        results.append(('code_executor_safe', ok))

        print('\n[2] CodeExecutor - security block (import os)')
        result = await registry.execute('code_executor', code="import os")
        print(f'    status={result.status.value}, error={result.error}')
        ok = result.status.value == 'error' and 'Security' in (result.error or '')
        results.append(('code_executor_security', ok))

        print('\n[3] CodeExecutor - runtime error handling')
        result = await registry.execute('code_executor', code="x = 1/0")
        print(f'    status={result.status.value}, error={result.error}')
        results.append(('code_executor_runtime_err', result.status.value == 'error'))

    # 4. Registry - unknown tool
    print('\n[4] Registry - unknown tool handling')
    result = await registry.execute('nonexistent_tool', x=1)
    print(f'    status={result.status.value}, error={result.error}')
    results.append(('registry_unknown', result.status.value == 'error' and 'not found' in result.error))

    # 5. Wikipedia - real API
    if 'wikipedia_search' in available:
        print('\n[5] Wikipedia - real API call')
        result = await registry.execute('wikipedia_search', query='Python programming language', sentences=2)
        print(f'    status={result.status.value}, duration={result.duration_ms:.0f}ms')
        if result.status.value == 'success':
            print(f'    title={result.data["title"]}')
            results.append(('wikipedia', True))
        else:
            print(f'    (network?) error={str(result.error)[:80]}')
            results.append(('wikipedia', False))

    # 6. DuckDuckGo - real search
    if 'web_search' in available:
        print('\n[6] DuckDuckGo - real search')
        result = await registry.execute('web_search', query='FastAPI framework')
        print(f'    status={result.status.value}, duration={result.duration_ms:.0f}ms')
        if result.status.value == 'success':
            print(f'    results={str(result.data.get("results", ""))[:80]}...')
            results.append(('duckduckgo', True))
        else:
            print(f'    (network/rate-limit?) error={str(result.error)[:80]}')
            results.append(('duckduckgo', False))

    # 7. ArXiv - real API
    if 'arxiv_search' in available:
        print('\n[7] ArXiv - real API')
        result = await registry.execute('arxiv_search', query='large language models', max_results=2)
        print(f'    status={result.status.value}, duration={result.duration_ms:.0f}ms')
        if result.status.value == 'success':
            print(f'    found={result.data["total_found"]} papers')
            for p in result.data['papers'][:2]:
                print(f'      - {p["title"][:60]}')
            results.append(('arxiv', True))
        else:
            print(f'    (network?) error={str(result.error)[:80]}')
            results.append(('arxiv', False))

    # 8. Browser - health check fail (PinchTab not running locally = graceful error)
    if 'browser' in available:
        print('\n[8] PinchTab - unreachable server (graceful error expected)')
        result = await registry.execute('browser', action='navigate', url='https://example.com')
        print(f'    status={result.status.value}, error={str(result.error)[:60]}')
        results.append(('browser_graceful', result.status.value == 'error'))

    # Summary
    print('\n' + '=' * 55)
    print('RESULTS:')
    passed = sum(1 for _, ok in results if ok)
    for name, ok in results:
        print(f'  {"PASS" if ok else "FAIL"} - {name}')
    print(f'\nTotal: {passed}/{len(results)} passed')
    print('=' * 55)

    sys.exit(0 if passed == len(results) and results else 1)

asyncio.run(main())
