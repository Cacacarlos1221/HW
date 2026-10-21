"""local_documents MCP server, stdio transport only."""
import argparse
import asyncio
from contextlib import asynccontextmanager
import logging
from pathlib import Path
from typing import Annotated, Literal
from mcp.server.fastmcp import FastMCP
from pydantic import Field
from index import LocalIndex

index = None

def invoke(fn, *args, **kwargs):
    try:
        return {'ok': True, 'data': fn(*args, **kwargs), 'error': None}
    except (ValueError, OSError) as exc:
        return {'ok': False, 'data': None, 'error': {'code': 'INVALID_OR_UNAVAILABLE', 'message': str(exc)}}

@asynccontextmanager
async def lifespan(_):
    global index
    index = await asyncio.to_thread(LocalIndex, config_path)
    async def refresh():
        while True:
            await asyncio.sleep(index.interval)
            result = await asyncio.to_thread(invoke, index.rebuild)
            if not result['ok']:
                logging.error('Refresh failed: %s', result['error'])
    task = asyncio.create_task(refresh())
    try:
        yield {}
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

mcp = FastMCP('local_documents', lifespan=lifespan)
Limit = Annotated[int, Field(ge=1, le=100, strict=True)]
Offset = Annotated[int, Field(ge=0, strict=True)]

@mcp.tool()
def local_browse(path: str | None = None, offset: Offset = 0, limit: Limit = 20) -> dict:
    """Browse direct children from the index, directories first. Omit path to list roots."""
    return invoke(index.browse, path, offset, limit)

@mcp.tool()
def local_search(query: Annotated[str, Field(max_length=256)] = '', kind: Literal['all', 'file', 'directory'] = 'all', extension: str | None = None, sort_by: Literal['relevance', 'modified', 'accessed'] = 'relevance', modified_since: float | None = None, accessed_since: float | None = None, offset: Offset = 0, limit: Limit = 20) -> dict:
    """Fuzzy filename/path search. Time filters use Unix seconds; accessed is OS atime, not reliable open history."""
    return invoke(index.search, query, kind, extension, sort_by, modified_since, accessed_since, offset, limit)

@mcp.tool()
def local_metadata(path: str) -> dict:
    """Read current filesystem metadata for one indexed path, never file contents."""
    return invoke(index.get_metadata, path)

@mcp.tool()
async def local_rebuild_index() -> dict:
    """Reload config and rebuild metadata index. Does not modify source files."""
    return await asyncio.to_thread(invoke, index.rebuild)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('config.json'))
    config_path = parser.parse_args().config
    logging.basicConfig(level=logging.INFO)
    mcp.run(transport='stdio')
