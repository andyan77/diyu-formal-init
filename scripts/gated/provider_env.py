"""Strictly read only the three authorized DeepSeek keys from one dotenv file."""

from __future__ import annotations

import re
import socket
import ssl
from pathlib import Path
from urllib.parse import urlsplit

AUTHORIZED_KEYS = (
    "DEEPSEEK_API_BASE_URL",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_MODEL",
)
_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


class ProviderHandshakeError(RuntimeError):
    """Fail closed before the formal suite spends a provider request."""


def probe_provider_tcp_tls(
    api_base_url: str,
    *,
    timeout_seconds: float = 5.0,
) -> dict[str, object]:
    """Prove direct TCP/TLS reachability without sending a completion request."""

    parsed = urlsplit(api_base_url)
    host = parsed.hostname or ""
    if parsed.scheme != "https" or not host:
        raise ProviderHandshakeError("provider base URL must name one HTTPS host")
    if host != "aliyuncs.com" and not host.endswith(".aliyuncs.com"):
        raise ProviderHandshakeError("provider host is outside the authorized mainland endpoint")
    port = parsed.port or 443
    try:
        # A raw socket deliberately ignores HTTP(S)/ALL_PROXY from the workstation.
        with socket.create_connection((host, port), timeout=timeout_seconds) as connection:
            context = ssl.create_default_context()
            with context.wrap_socket(connection, server_hostname=host) as tls_connection:
                tls_version = tls_connection.version() or "unknown"
    except (OSError, ssl.SSLError) as exc:
        raise ProviderHandshakeError("provider TCP/TLS handshake failed") from exc
    return {
        "completion_requests": 0,
        "host": host,
        "port": port,
        "probe_version": "gate-d-provider-tcp-tls-v1",
        "provider_budget_consumed": 0,
        "status": "PASS",
        "tls": True,
        "tls_version": tls_version,
    }


def _value(raw: str) -> str:
    candidate = raw.strip()
    if not candidate:
        return ""
    if candidate[0] in {'"', "'"}:
        quote = candidate[0]
        if len(candidate) < 2 or candidate[-1] != quote:
            raise ValueError("authorized dotenv value has unmatched quotes")
        candidate = candidate[1:-1]
    elif " #" in candidate:
        candidate = candidate.split(" #", maxsplit=1)[0].rstrip()
    if "\n" in candidate or "\r" in candidate or "\\n" in candidate or "\\r" in candidate:
        raise ValueError("authorized dotenv value must be one physical line")
    return candidate


def parse_authorized_deepseek_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ValueError("authorized dotenv file is unavailable")
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, raw_value = line.partition("=")
        key = key.strip()
        if not separator or _KEY.fullmatch(key) is None:
            raise ValueError("dotenv contains a malformed physical line")
        if key not in AUTHORIZED_KEYS:
            continue
        if key in result:
            raise ValueError(f"dotenv repeats authorized key {key}")
        result[key] = _value(raw_value)
    if set(result) != set(AUTHORIZED_KEYS) or any(not result[key] for key in AUTHORIZED_KEYS):
        raise ValueError("the three authorized DeepSeek keys must be present and non-empty")
    return result
