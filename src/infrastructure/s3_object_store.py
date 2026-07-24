from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit
from uuid import UUID

import httpx

from src.ports.material_object_store import MaterialObjectStore


class S3ObjectStore(MaterialObjectStore):
    """Small S3-compatible storage adapter using path-style SigV4 requests."""

    _ALLOWED_SUFFIXES = {
        ".txt",
        ".md",
        ".csv",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".mp4",
        ".mov",
        ".m4v",
    }

    def __init__(
        self,
        endpoint_url: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        region: str,
    ) -> None:
        parsed = urlsplit(endpoint_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("对象存储地址无效")
        self._endpoint_url = endpoint_url.rstrip("/")
        self._host = parsed.netloc
        self._bucket = bucket
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._region = region

    def put(self, asset_id: UUID, suffix: str, payload: bytes) -> str:
        normalized_suffix = suffix.lower() if suffix.startswith(".") else ""
        if normalized_suffix not in self._ALLOWED_SUFFIXES:
            raise ValueError("素材文件类型不受支持")
        object_key = f"materials/{asset_id}{normalized_suffix}"
        self._request("PUT", object_key, payload)
        return object_key

    def delete(self, object_key: str) -> None:
        if not object_key.startswith("materials/") or ".." in object_key:
            raise ValueError("素材对象标识无效")
        self._request("DELETE", object_key)

    def is_ready(self) -> bool:
        try:
            self._request("HEAD", "")
        except httpx.HTTPError:
            return False
        return True

    def _request(self, method: str, object_key: str, body: bytes = b"") -> None:
        now = datetime.now(timezone.utc)
        date_stamp = now.strftime("%Y%m%d")
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        path = "/" + quote(self._bucket, safe="-_.~")
        if object_key:
            path += "/" + quote(object_key, safe="/-_.~")
        body_hash = hashlib.sha256(body).hexdigest()
        canonical_headers = f"host:{self._host}\nx-amz-content-sha256:{body_hash}\nx-amz-date:{amz_date}\n"
        signed_headers = "host;x-amz-content-sha256;x-amz-date"
        canonical_request = "\n".join((method, path, "", canonical_headers, signed_headers, body_hash))
        credential_scope = f"{date_stamp}/{self._region}/s3/aws4_request"
        string_to_sign = "\n".join(
            (
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            )
        )
        signing_key = self._signing_key(date_stamp)
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authorization = (
            "AWS4-HMAC-SHA256 "
            f"Credential={self._access_key_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        response = httpx.request(
            method,
            f"{self._endpoint_url}{path}",
            content=body,
            headers={
                "Authorization": authorization,
                "x-amz-content-sha256": body_hash,
                "x-amz-date": amz_date,
            },
            timeout=15.0,
        )
        response.raise_for_status()

    def _signing_key(self, date_stamp: str) -> bytes:
        key = ("AWS4" + self._secret_access_key).encode("utf-8")
        date_key = hmac.new(key, date_stamp.encode("utf-8"), hashlib.sha256).digest()
        region_key = hmac.new(date_key, self._region.encode("utf-8"), hashlib.sha256).digest()
        service_key = hmac.new(region_key, b"s3", hashlib.sha256).digest()
        return hmac.new(service_key, b"aws4_request", hashlib.sha256).digest()
