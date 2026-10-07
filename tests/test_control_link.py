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


async def start_daemon() -> tuple[ChromeAgentDaemon, asyncio.Task]:
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
    return daemon, task


async def connect_extension(
    daemon: ChromeAgentDaemon, extension_id: str = "test-extension"
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Pose as the extension: register, and stay connected."""
    reader, writer = await asyncio.open_unix_connection(str(daemon.socket_path))
    await send_message(
        writer,
        {
            "jsonrpc": "2.0",
            "id": "register-1",
            "method": "session.register",
            "params": {"extensionId": extension_id},
        },
    )
    assert (await read_message(reader))["result"]["status"] == "registered"
    return reader, writer


async def close(*writers: asyncio.StreamWriter) -> None:
    for writer in writers:
        writer.close()
    for writer in writers:
        await asyncio.wait_for(writer.wait_closed(), timeout=2)


@pytest.mark.asyncio
async def test_request_round_trip_through_extension():
    daemon, task = await start_daemon()
    extension_reader, extension_writer = await connect_extension(daemon)

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

    await close(client_writer, extension_writer)
    await daemon.stop()
    await asyncio.wait_for(task, timeout=2)


@pytest.mark.asyncio
async def test_extension_reload_is_forwarded_and_answered():
    """The reload command reaches the extension and its answer comes back."""
    daemon, task = await start_daemon()
    extension_reader, extension_writer = await connect_extension(daemon)

    client_reader, client_writer = await asyncio.open_unix_connection(str(daemon.socket_path))
    await send_message(
        client_writer,
        {
            "jsonrpc": "2.0",
            "id": "client-1",
            "method": "extension.reload",
            "params": {},
        },
    )

    forwarded = await read_message(extension_reader)
    assert forwarded["method"] == "extension.reload"
    await send_message(
        extension_writer,
        {
            "jsonrpc": "2.0",
            "id": forwarded["id"],
            "result": {"reloading": True},
        },
    )
    response = await read_message(client_reader)
    assert response["result"]["reloading"] is True

    await close(client_writer, extension_writer)
    await daemon.stop()
    await asyncio.wait_for(task, timeout=2)


@pytest.mark.asyncio
async def test_a_disconnect_fails_the_request_instead_of_waiting_out_the_timeout():
    """A reloading extension drops its own connection on the way out.

    The request it owed then has no one left to answer it. Waiting the full
    forwarding timeout for a reply that cannot come is what this covers: the
    caller hears about the disconnect instead.
    """
    daemon, task = await start_daemon()
    extension_reader, extension_writer = await connect_extension(daemon)

    client_reader, client_writer = await asyncio.open_unix_connection(str(daemon.socket_path))
    await send_message(
        client_writer,
        {
            "jsonrpc": "2.0",
            "id": "client-1",
            "method": "extension.reload",
            "params": {},
        },
    )
    assert (await read_message(extension_reader))["method"] == "extension.reload"

    # Away it goes, without answering.
    await close(extension_writer)

    started = asyncio.get_running_loop().time()
    response = await asyncio.wait_for(read_message(client_reader), timeout=5)
    elapsed = asyncio.get_running_loop().time() - started

    assert elapsed < 5, "the caller waited for a reply that could not come"
    assert "disconnected" in response["result"]["error"].lower()

    await close(client_writer)
    await daemon.stop()
    await asyncio.wait_for(task, timeout=2)


@pytest.mark.asyncio
async def test_sites_list_is_forwarded_and_answered():
    """Who is authorized is Chrome's answer; the daemon only carries it."""
    daemon, task = await start_daemon()
    extension_reader, extension_writer = await connect_extension(daemon)

    client_reader, client_writer = await asyncio.open_unix_connection(str(daemon.socket_path))
    await send_message(
        client_writer,
        {"jsonrpc": "2.0", "id": "client-1", "method": "sites.list", "params": {}},
    )

    forwarded = await read_message(extension_reader)
    assert forwarded["method"] == "sites.list"
    await send_message(
        extension_writer,
        {
            "jsonrpc": "2.0",
            "id": forwarded["id"],
            "result": {"origins": ["https://example.com/*"]},
        },
    )
    response = await read_message(client_reader)
    assert response["result"]["origins"] == ["https://example.com/*"]

    await close(client_writer, extension_writer)
    await daemon.stop()
    await asyncio.wait_for(task, timeout=2)


@pytest.mark.asyncio
async def test_sites_revoke_carries_the_origin_through_untouched():
    """The daemon must not normalize the origin; the extension decides that."""
    daemon, task = await start_daemon()
    extension_reader, extension_writer = await connect_extension(daemon)

    client_reader, client_writer = await asyncio.open_unix_connection(str(daemon.socket_path))
    await send_message(
        client_writer,
        {
            "jsonrpc": "2.0",
            "id": "client-1",
            "method": "sites.revoke",
            "params": {"origin": "https://example.com"},
        },
    )

    forwarded = await read_message(extension_reader)
    assert forwarded["method"] == "sites.revoke"
    assert forwarded["params"] == {"origin": "https://example.com"}
    await send_message(
        extension_writer,
        {
            "jsonrpc": "2.0",
            "id": forwarded["id"],
            "result": {
                "revoked": True,
                "granted": True,
                "origin": "https://example.com/*",
            },
        },
    )
    response = await read_message(client_reader)
    assert response["result"]["revoked"] is True

    await close(client_writer, extension_writer)
    await daemon.stop()
    await asyncio.wait_for(task, timeout=2)
