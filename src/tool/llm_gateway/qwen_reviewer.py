from __future__ import annotations

import json
import logging
from typing import cast

import httpx

from src.ports.reviewer_provider import (
    ReviewerProvider,
    ReviewerProviderResult,
)
from src.shared.clause_license import (
    CLAUSE_LICENSE_TOOL_NAME,
    ClauseLicenseReviewsV1,
    ClauseLicenseV1,
    clause_license_review_json_schema,
    parse_clause_license_reviews_v1,
)
from src.shared.errors import GenerationFailed

_LOGGER = logging.getLogger(__name__)


class QwenReviewerProvider(ReviewerProvider):
    """Single-call Qwen Reviewer over the China-region compatible Responses API."""

    def __init__(
        self,
        *,
        api_base_url: str,
        api_key: str,
        model: str,
    ) -> None:
        self._api_base_url = api_base_url.rstrip("/")
        self._api_key = api_key
        self._model = model

    @property
    def provider_name(self) -> str:
        return "dashscope"

    @property
    def model_name(self) -> str:
        return self._model

    def review(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        licenses: tuple[ClauseLicenseV1, ...],
        timeout_seconds: float,
    ) -> ReviewerProviderResult:
        if not licenses:
            raise GenerationFailed("Reviewer 缺少待核对的 clause 许可证")
        request_payload: dict[str, object] = {
            "model": self._model,
            "instructions": system_prompt,
            "input": user_prompt,
            "reasoning": {"effort": "high"},
            "tools": [
                {
                    "type": "function",
                    "name": CLAUSE_LICENSE_TOOL_NAME,
                    "description": (
                        "Check whether every writer clause is fully supported by its "
                        "server-assigned ClauseLicenseV1."
                    ),
                    "parameters": clause_license_review_json_schema(licenses),
                }
            ],
            "tool_choice": "required",
            "store": False,
        }
        try:
            with httpx.Client(
                timeout=httpx.Timeout(timeout_seconds),
            ) as client:
                response = client.post(
                    f"{self._api_base_url}/responses",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=request_payload,
                )
        except httpx.TransportError as exc:
            raise GenerationFailed("Reviewer 模型网络请求失败") from exc
        if response.status_code >= 400:
            _LOGGER.warning(
                "Qwen Reviewer request rejected: status=%s",
                response.status_code,
            )
            raise GenerationFailed("Reviewer 模型服务拒绝当前请求")
        try:
            payload = response.json()
        except (TypeError, ValueError) as exc:
            raise GenerationFailed("Reviewer 模型返回无效") from exc
        if not isinstance(payload, dict):
            raise GenerationFailed("Reviewer 模型返回无效")
        try:
            reviews = self._parse_response(
                cast(dict[str, object], payload),
                licenses=licenses,
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            raise GenerationFailed("Reviewer 许可证据不完整") from exc
        return ReviewerProviderResult(
            reviews=reviews,
            raw_payload=cast(dict[str, object], payload),
            retry_count=0,
        )

    @staticmethod
    def _parse_response(
        payload: dict[str, object],
        *,
        licenses: tuple[ClauseLicenseV1, ...],
    ) -> ClauseLicenseReviewsV1:
        if payload.get("status") != "completed" or payload.get("error") is not None:
            raise TypeError("reviewer response status is invalid")
        output = payload.get("output")
        if not isinstance(output, list):
            raise TypeError("reviewer response output is invalid")
        function_calls = [
            item
            for item in output
            if isinstance(item, dict) and item.get("type") == "function_call"
        ]
        unexpected = [
            item
            for item in output
            if not (
                isinstance(item, dict)
                and item.get("type") in {"reasoning", "function_call"}
            )
        ]
        if unexpected or len(function_calls) != 1:
            raise TypeError("reviewer function call count is invalid")
        function_call = function_calls[0]
        if function_call.get("name") != CLAUSE_LICENSE_TOOL_NAME:
            raise TypeError("reviewer function name is invalid")
        arguments = function_call.get("arguments")
        if not isinstance(arguments, str):
            raise TypeError("reviewer function arguments are invalid")
        return parse_clause_license_reviews_v1(
            json.loads(arguments),
            licenses=licenses,
        )
