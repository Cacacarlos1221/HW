"""Run: python test_smoke.py (includes real MCP stdio roundtrip)."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from index import LocalIndex

async def main():
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        root = base / 'documents'
        root.mkdir()
        (root / 'folder').mkdir()
        (root / 'report.txt').write_text('demo')
        (root / '.secret').write_text('hidden')
        outside = base / 'outside.txt'
        outside.write_text('outside')
        try:
            (root / 'escape').symlink_to(outside)
        except OSError:
            pass
        config = base / 'config.json'
        config.write_text(json.dumps({'dirs': [str(root)], 'refresh_interval_seconds': 1}))
        idx = LocalIndex(config)
        assert idx.browse(str(root), limit=1)['items'][0]['kind'] == 'directory'
        assert idx.browse(str(root), limit=1)['next_offset'] == 1
        assert idx.search('reprot.txt', kind='file', extension='.txt')['total'] == 1
        assert idx.search('.secret')['total'] == 0
        assert idx.search('escape')['total'] == 0
        for path in [outside, root / '..' / 'outside.txt']:
            try:
                idx.get_metadata(str(path))
            except ValueError:
                pass
            else:
                raise AssertionError('Outside path was accepted')
        params = StdioServerParameters(command=sys.executable, args=[str(Path(__file__).with_name('server.py')), '--config', str(config)])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert {t.name for t in tools.tools} == {'local_browse', 'local_search', 'local_metadata', 'local_rebuild_index'}
                schema = next(t.inputSchema for t in tools.tools if t.name == 'local_search')
                assert schema['properties']['limit']['maximum'] == 100
                assert schema['properties']['kind']['enum'] == ['all', 'file', 'directory']
                result = await session.call_tool('local_search', {'query': 'report'})
                payload = json.loads(result.content[0].text)
                assert payload['ok'] and payload['data']['total'] == 1
                result = await session.call_tool('local_metadata', {'path': str(outside)})
                assert not json.loads(result.content[0].text)['ok']
                result = await session.call_tool('local_browse', {'limit': 101})
                assert result.isError
                (root / 'added.md').write_text('new')
                for _ in range(30):
                    await asyncio.sleep(0.1)
                    result = await session.call_tool('local_search', {'query': 'added.md'})
                    if json.loads(result.content[0].text)['data']['total'] == 1:
                        break
                else:
                    raise AssertionError('Periodic refresh failed')
                (root / 'report.txt').unlink()
                result = await session.call_tool('local_rebuild_index', {})
                assert json.loads(result.content[0].text)['ok']
                result = await session.call_tool('local_search', {'query': 'report', 'extension': 'txt'})
                assert json.loads(result.content[0].text)['data']['total'] == 0
    print('PASS: index, boundaries, schema, stdio, tools, periodic refresh, rebuild')

if __name__ == '__main__':
    asyncio.run(main())
