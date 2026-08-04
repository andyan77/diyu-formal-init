from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from src.tool import ssh_connect_proxy
from src.tool.ssh_connect_proxy import SshConnectProxyConfig


def _config() -> SshConnectProxyConfig:
    return SshConnectProxyConfig(
        allowed_authority="api.deepseek.com:443",
        ssh_host="root@example.test",
        ssh_key="/private/key",
        ssh_control_path="var/tmp/control/master",
    )


def test_ssh_connect_proxy_reuses_one_persistent_control_master() -> None:
    command = ssh_connect_proxy._ssh_command(_config())

    assert command.count("ControlMaster=auto") == 1
    assert command.count("ControlPersist=300") == 1
    assert command.count("var/tmp/control/master") == 1
    assert command.count("ServerAliveInterval=15") == 1
    assert command.count("ServerAliveCountMax=3") == 1
    assert command[-3:] == (
        "-W",
        "api.deepseek.com:443",
        "root@example.test",
    )


class _MemoryWriter:
    def __init__(self) -> None:
        self.data = bytearray()
        self.closed = False

    def write(self, value: bytes) -> None:
        self.data.extend(value)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


class _FailedProcess:
    def __init__(self) -> None:
        self.returncode: int | None = 255
        self.stdin = _MemoryWriter()
        self.stdout = asyncio.StreamReader()
        self.stdout.feed_eof()

    async def wait(self) -> int:
        return 255

    def terminate(self) -> None:
        self.returncode = 255


def test_ssh_connect_proxy_never_reports_200_for_failed_ssh_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _FailedProcess()

    async def create_process(*_args: object, **_kwargs: object) -> _FailedProcess:
        return process

    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        create_process,
    )
    monkeypatch.setattr(
        ssh_connect_proxy,
        "_control_master_available",
        lambda _config: True,
    )

    async def exercise() -> bytes:
        reader = asyncio.StreamReader()
        reader.feed_data(
            b"CONNECT api.deepseek.com:443 HTTP/1.1\r\n"
            b"Host: api.deepseek.com:443\r\n\r\n"
        )
        reader.feed_eof()
        writer = _MemoryWriter()
        await ssh_connect_proxy._handle(
            reader,
            cast(Any, writer),
            config=_config(),
            establishment_grace_seconds=0.01,
        )
        assert writer.closed is True
        return bytes(writer.data)

    response = asyncio.run(exercise())

    assert response.startswith(b"HTTP/1.1 502 Bad Gateway")
    assert b"200 Connection Established" not in response
