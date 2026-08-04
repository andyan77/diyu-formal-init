from __future__ import annotations

import argparse
import asyncio
import os
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

_MAX_REQUEST_BYTES = 16 * 1024
_SSH_ESTABLISHMENT_GRACE_SECONDS = 0.25


@dataclass(frozen=True)
class SshConnectProxyConfig:
    allowed_authority: str
    ssh_host: str
    ssh_key: str
    ssh_control_path: str
    ssh_connect_timeout_seconds: int = 10
    ssh_control_persist_seconds: int = 300


def _ssh_command(config: SshConnectProxyConfig) -> tuple[str, ...]:
    return (
        "ssh",
        "-S",
        config.ssh_control_path,
        "-i",
        config.ssh_key,
        "-o",
        "BatchMode=yes",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ControlMaster=auto",
        "-o",
        f"ControlPersist={config.ssh_control_persist_seconds}",
        "-o",
        f"ConnectTimeout={config.ssh_connect_timeout_seconds}",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=3",
        "-W",
        config.allowed_authority,
        config.ssh_host,
    )


def _control_master_available(config: SshConnectProxyConfig) -> bool:
    return Path(config.ssh_control_path).is_socket()


async def _pipe(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    try:
        while chunk := await reader.read(64 * 1024):
            writer.write(chunk)
            await writer.drain()
    finally:
        with suppress(Exception):
            writer.close()


async def _ssh_stream_established(
    process: asyncio.subprocess.Process,
    *,
    grace_seconds: float = _SSH_ESTABLISHMENT_GRACE_SECONDS,
) -> bool:
    try:
        await asyncio.wait_for(
            asyncio.shield(process.wait()),
            timeout=grace_seconds,
        )
    except asyncio.TimeoutError:
        return process.returncode is None
    return False


async def _respond(
    writer: asyncio.StreamWriter,
    status: bytes,
) -> None:
    writer.write(b"HTTP/1.1 " + status + b"\r\nConnection: close\r\n\r\n")
    await writer.drain()


async def _handle(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    *,
    config: SshConnectProxyConfig,
    establishment_grace_seconds: float = _SSH_ESTABLISHMENT_GRACE_SECONDS,
) -> None:
    process: asyncio.subprocess.Process | None = None
    try:
        request = await client_reader.readuntil(b"\r\n\r\n")
        if len(request) > _MAX_REQUEST_BYTES:
            raise ValueError("proxy request is too large")
        request_line = request.split(b"\r\n", 1)[0].decode("ascii")
        method, authority, _version = request_line.split(" ", 2)
        if (
            method != "CONNECT"
            or authority.casefold() != config.allowed_authority.casefold()
        ):
            await _respond(client_writer, b"403 Forbidden")
            return
        if not _control_master_available(config):
            await _respond(client_writer, b"502 Bad Gateway")
            return
        try:
            process = await asyncio.create_subprocess_exec(
                *_ssh_command(config),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError:
            await _respond(client_writer, b"502 Bad Gateway")
            return
        if not await _ssh_stream_established(
            process,
            grace_seconds=establishment_grace_seconds,
        ):
            await _respond(client_writer, b"502 Bad Gateway")
            return
        assert process.stdin is not None and process.stdout is not None
        client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await client_writer.drain()
        await asyncio.gather(
            _pipe(client_reader, process.stdin),
            _pipe(process.stdout, client_writer),
        )
    except (asyncio.IncompleteReadError, UnicodeError, ValueError):
        with suppress(Exception):
            await _respond(client_writer, b"400 Bad Request")
    finally:
        with suppress(Exception):
            client_writer.close()
            await client_writer.wait_closed()
        if process is not None:
            if process.returncode is None:
                process.terminate()
            with suppress(Exception):
                await asyncio.wait_for(process.wait(), timeout=5)


async def _serve(arguments: argparse.Namespace) -> None:
    config = SshConnectProxyConfig(
        allowed_authority=arguments.allowed_authority,
        ssh_host=arguments.ssh_host,
        ssh_key=arguments.ssh_key,
        ssh_control_path=arguments.ssh_control_path,
    )
    server = await asyncio.start_server(
        lambda reader, writer: _handle(reader, writer, config=config),
        host="127.0.0.1",
        port=arguments.port,
    )
    async with server:
        await server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allowed-authority", required=True)
    parser.add_argument("--ssh-host", required=True)
    parser.add_argument("--ssh-key", required=True)
    parser.add_argument("--ssh-control-path", required=True)
    parser.add_argument("--port", required=True, type=int)
    arguments = parser.parse_args()
    control_path = Path(str(arguments.ssh_control_path))
    control_parent = control_path.parent
    if (
        not control_parent.is_dir()
        or control_parent.stat().st_mode & 0o077
        or not control_path.is_socket()
    ):
        parser.error("SSH control path must be an active socket inside a private directory")
    os.umask(0o077)
    asyncio.run(_serve(arguments))


if __name__ == "__main__":
    main()
