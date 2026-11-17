from __future__ import annotations

from contextlib import asynccontextmanager
from fastmcp import Client


@asynccontextmanager
async def open_local_session(server_params):
    async with Client(server_params) as session:
        yield session
