"""Full-duplex CLI-side request routing through a persistent extension session."""

import asyncio
import json
import struct
import uuid
from pathlib import Path

import pytest

from chrome_agent.daemon.daemon import ChromeAgentDaemon


async def send_message(writer: asyncio.StreamWriter, message: dict) -> None:
    payload = json.dumps(message).encode()
    writer.write(struct.pack("<I", len(payload)) + payload)
    await writer.drain()


async def read_message(reader: asyncio.StreamReader) -> dict:
    prefix = await asyncio.wait_for(reader.readexactly(4), timeout=2)
    length = struct.unpack("<I", prefix)[0]
    payload = await asyncio.wait_for(reader.readexactly(length), timeout=2)
    return json.loads(payload.decode())


@pytest.mark.asyncio
async def test_request_round_trip_through_extension():
    daemon = ChromeAgentDaemon()
    daemon.socket_path = Path("/tmp") / f"chrome-agent-test-{uuid.uuid4().hex[:8]}.sock"
    task = asyncio.create_task(daemon.start())
    for _ in range(200):
        if daemon.running:
            break
        if task.done():
            task.result()
        await asyncio.sleep(0.01)
    assert daemon.running

    extension_reader, extension_writer = await asyncio.open_unix_connection(str(daemon.socket_path))
    await send_message(
        extension_writer,
        {
            "jsonrpc": "2.0",
            "id": "register-1",
            "method": "session.register",
            "params": {"extensionId": "test-extension"},
        },
    )
    assert (await read_message(extension_reader))["result"]["status"] == "registered"

    client_reader, client_writer = await asyncio.open_unix_connection(str(daemon.socket_path))
    await send_message(
        client_writer,
        {
            "jsonrpc": "2.0",
            "id": "client-1",
            "method": "tabs.list",
            "params": {"domain": "xiaohongshu.com"},
        },
    )

    forwarded = await read_message(extension_reader)
    assert forwarded["method"] == "tabs.list"
    await send_message(
        extension_writer,
        {
            "jsonrpc": "2.0",
            "id": forwarded["id"],
            "result": {"tabs": [{"id": 7, "url": "https://www.xiaohongshu.com/"}]},
        },
    )
    response = await read_message(client_reader)
    assert response["result"]["tabs"][0]["id"] == 7

    client_writer.close()
    extension_writer.close()
    await asyncio.wait_for(client_writer.wait_closed(), timeout=2)
    await asyncio.wait_for(extension_writer.wait_closed(), timeout=2)
    await daemon.stop()
    await asyncio.wait_for(task, timeout=2)
