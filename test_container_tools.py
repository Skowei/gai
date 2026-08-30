#!/usr/bin/env python3
"""Test remaining tools inside container: arxiv, browser, documents"""
import asyncio
from app.core.agent.tools import registry


async def main():
    # ArXiv
    r = await registry.execute('arxiv_search', query='transformer architecture', max_results=2)
    if r.is_success:
        print(f"[arxiv] {r.status.value}: found={r.data.get('total_found')} papers")
        for p in r.data.get('papers', [])[:2]:
            print(f"   - {p['title'][:70]}")
    else:
        print(f"[arxiv] {r.status.value}: {r.error[:120]}")

    # Browser - navigate (PinchTab security allows localhost)
    r = await registry.execute('browser', action='navigate', url='http://127.0.0.1:9868/')
    print(f"[browser nav] {r.status.value}: {str(r.data)[:120] if r.is_success else r.error[:120]}")

    # Browser - snapshot
    r = await registry.execute('browser', action='snapshot')
    if r.is_success:
        print(f"[browser snap] {r.status.value}: elements={r.data.get('element_count')}")
    else:
        print(f"[browser snap] {r.status.value}: {r.error[:120]}")

    # Browser - extract text
    r = await registry.execute('browser', action='extract')
    if r.is_success:
        print(f"[browser text] {r.status.value}: length={r.data.get('length')}")
    else:
        print(f"[browser text] {r.status.value}: {r.error[:120]}")

    # Browser - screenshot
    r = await registry.execute('browser', action='screenshot')
    print(f"[browser shot] {r.status.value}: {str(r.data)[:120] if r.is_success else r.error[:120]}")

    # Document converter (real vault file)
    r = await registry.execute('document_converter', file_path='/app/obsidian_vault/knowledge_base/fact_enterprise_test_3.md')
    if r.is_success:
        print(f"[docconvert] {r.status.value}: length={r.data['length']}, content={r.data['markdown'][:80]!r}")
    else:
        print(f"[docconvert] {r.status.value}: {r.error[:150]}")

    print('Registered tools:', registry.list_tools())


asyncio.run(main())
