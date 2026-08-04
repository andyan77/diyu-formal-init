from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import cast
from uuid import UUID

from src.infrastructure.workbench_repository import PostgresWorkbenchRepository
from src.shared.errors import DomainError
from src.shared.tenant_brand_sources import SourceDocumentDraft, freeze_source_batch
from src.shared.types import TenantManagementScope

_ALLOWED_PRODUCTS = frozenset(
    {
        "dressing_decision",
        "product_truth",
        "brand_life_narrative",
        "local_response",
        "visual_styling_story",
    }
)
_ROLE_TO_KIND = {
    "public_brand_fact": "brand_fact",
    "expression_constraint": "expression_constraint",
    "creative_method": "creative_method",
}


def _dictionary(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise DomainError(message)
    return cast(dict[str, object], value)


def _list(value: object, message: str) -> list[object]:
    if not isinstance(value, list):
        raise DomainError(message)
    return cast(list[object], value)


def _text(value: object, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainError(message)
    return value.strip()


def _published_text(exact_text: str) -> str:
    text = exact_text.strip()
    if text.startswith(">"):
        text = text[1:].strip()
    if (
        not text
        or text.startswith(("|", "#", "- ", "* "))
        or text == "---"
        or len(text) > 1200
    ):
        raise DomainError("所选来源 segment 不是可直接确认的自然品牌表达")
    return text


def compile_selection(
    documents: tuple[SourceDocumentDraft, ...],
    config: object,
) -> tuple[dict[str, object], ...]:
    document = _dictionary(config, "正式发布选择配置无效")
    if document.get("schema_version") != "tenant01-formal-publication-selection-v1":
        raise DomainError("正式发布选择配置版本无效")
    if document.get("source_contract_version") != "tenant-brand-source-v1":
        raise DomainError("正式发布选择与来源合同不一致")
    by_source_locator = {
        (source.source_id, segment.source_locator): (source, segment)
        for source in documents
        for segment in source.segments
    }
    compiled: list[dict[str, object]] = []
    for position, raw in enumerate(
        _list(document.get("items"), "正式发布选择缺少条目"), start=1
    ):
        item = _dictionary(raw, "正式发布选择条目无效")
        source_id = _text(item.get("source_id"), "正式发布选择缺少 source_id")
        source_locator = _text(
            item.get("source_locator"), "正式发布选择缺少 source_locator"
        )
        source = by_source_locator.get((source_id, source_locator))
        if source is None:
            raise DomainError("正式发布选择无法绑定冻结来源 segment")
        source_document, segment = source
        if source_document.activation_status != "brand_user_authorized":
            raise DomainError("模板或未授权来源不能进入正式发布投影")
        if (
            item.get("source_version") != source_document.source_version
            or item.get("source_document_digest")
            != source_document.normalized_sha256
            or item.get("source_segment_digest") != segment.digest
        ):
            raise DomainError("正式发布选择的来源版本或 digest 漂移")
        role = _text(item.get("publication_role"), "正式发布选择缺少角色")
        if _ROLE_TO_KIND.get(role) != segment.semantic_kind:
            raise DomainError("正式发布选择角色超过来源 segment 语义等级")
        applicability = tuple(
            _text(value, "正式发布适用内容无效")
            for value in _list(item.get("applicability"), "正式发布适用内容缺失")
        )
        if (
            not applicability
            or len(applicability) != len(set(applicability))
            or not set(applicability) <= _ALLOWED_PRODUCTS
        ):
            raise DomainError("正式发布选择必须具有不重复的合法适用内容")
        compiled.append(
            {
                "position": position,
                "source_id": source_id,
                "source_version": source_document.source_version,
                "source_document_digest": source_document.normalized_sha256,
                "source_locator": source_locator,
                "source_segment_digest": segment.digest,
                "publication_role": role,
                "applicability": list(applicability),
                "published_text": _published_text(segment.exact_text),
                "source_query": segment.exact_text,
            }
        )
    if not 1 < len(compiled) <= 64:
        raise DomainError("正式发布选择必须包含 2 到 64 个最小充分条目")
    if len({(item["source_id"], item["source_locator"]) for item in compiled}) != len(
        compiled
    ):
        raise DomainError("正式发布选择重复使用同一来源 segment")
    if {str(item["publication_role"]) for item in compiled} != set(_ROLE_TO_KIND):
        raise DomainError("正式发布选择必须同时覆盖品牌事实、表达边界和创作方法")
    if {
        product
        for item in compiled
        for product in cast(list[str], item["applicability"])
    } != _ALLOWED_PRODUCTS:
        raise DomainError("正式发布选择没有覆盖所有现有内容产品")
    return tuple(compiled)


def _resolve_items(
    repository: PostgresWorkbenchRepository,
    scope: TenantManagementScope,
    selection: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], ...]:
    resolved: list[dict[str, object]] = []
    for selected in selection:
        options = repository.publication_source_options(
            scope,
            str(selected["source_query"]),
        )
        matches = [
            option
            for option in options
            if option.get("source_id") == selected["source_id"]
            and option.get("source_version") == selected["source_version"]
            and option.get("source_document_digest")
            == selected["source_document_digest"]
            and option.get("source_locator") == selected["source_locator"]
            and option.get("source_digest") == selected["source_segment_digest"]
            and option.get("semantic_kind")
            == _ROLE_TO_KIND[str(selected["publication_role"])]
        ]
        if len(matches) != 1:
            raise DomainError("正式管理员无法唯一解析所选来源 segment")
        resolved.append(
            {
                "source_segment_id": matches[0]["source_segment_id"],
                "publication_role": selected["publication_role"],
                "published_text": selected["published_text"],
                "applicability": selected["applicability"],
            }
        )
    return tuple(resolved)


def apply_confirmed_projection(
    *,
    repository: PostgresWorkbenchRepository,
    scope: TenantManagementScope,
    selection: tuple[dict[str, object], ...],
) -> dict[str, object]:
    resolved = _resolve_items(repository, scope, selection)
    existing = repository.brand_publication_projection(scope)
    existing_current = existing.get("current")
    if isinstance(existing_current, dict) and existing_current.get("status") == "confirmed":
        raw_existing_items = existing_current.get("items")
        if isinstance(raw_existing_items, list) and len(raw_existing_items) == len(resolved):
            comparable_existing = [
                {
                    "source_segment_id": item.get("source_segment_id"),
                    "publication_role": item.get("publication_role"),
                    "published_text": item.get("published_text"),
                    "applicability": item.get("applicability"),
                }
                for item in raw_existing_items
                if isinstance(item, dict)
            ]
            if comparable_existing == list(resolved):
                return existing
    candidate = repository.create_brand_publication_candidate(scope, resolved)
    confirmed = repository.confirm_brand_publication_projection(
        scope, UUID(str(candidate["id"]))
    )
    projection = repository.brand_publication_projection(scope)
    current = _dictionary(projection.get("current"), "确认后当前发布版本缺失")
    if (
        current.get("id") != confirmed.get("id")
        or current.get("status") != "confirmed"
        or current.get("digest") != candidate.get("digest")
        or len(_list(current.get("items"), "确认后发布条目缺失")) != len(selection)
    ):
        raise DomainError("正式发布投影确认后回读不一致")
    return projection


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate or confirm the source-bound TENANT-01 brand projection."
    )
    parser.add_argument("action", choices=("validate", "apply"))
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/tenant01/formal-publication-v1.json"),
    )
    parser.add_argument("--tenant-id", type=UUID)
    parser.add_argument("--manager-user-id", type=UUID)
    parser.add_argument("--brand-id", type=UUID)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    documents = freeze_source_batch(args.source_root.resolve(strict=True))
    config = json.loads(args.config.resolve(strict=True).read_text(encoding="utf-8"))
    selection = compile_selection(documents, config)
    if args.action == "validate":
        print(
            json.dumps(
                {
                    "documents": len(documents),
                    "segments": sum(len(document.segments) for document in documents),
                    "selected_items": len(selection),
                    "roles": dict(
                        sorted(
                            {
                                role: sum(
                                    item["publication_role"] == role for item in selection
                                )
                                for role in _ROLE_TO_KIND
                            }.items()
                        )
                    ),
                    "verdict": "PASS",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    if args.tenant_id is None or args.manager_user_id is None or args.brand_id is None:
        raise DomainError("apply 必须明确正式租户、管理员和品牌 ID")
    database_url = os.environ.get("DIYU_APP_DATABASE_URL", "")
    if not database_url:
        raise DomainError("缺少受控应用数据库连接")
    projection = apply_confirmed_projection(
        repository=PostgresWorkbenchRepository(database_url),
        scope=TenantManagementScope(
            args.tenant_id,
            args.manager_user_id,
            args.brand_id,
        ),
        selection=selection,
    )
    if args.output is not None:
        args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        args.output.parent.chmod(0o700)
        args.output.write_text(
            json.dumps(projection, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        args.output.chmod(0o600)
    current = _dictionary(projection.get("current"), "当前发布版本缺失")
    print(
        json.dumps(
            {
                "projection_id": current["id"],
                "version": current["version"],
                "digest": current["digest"],
                "items": len(_list(current["items"], "当前发布条目缺失")),
                "verdict": "PASS",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
