from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, cast

from src.shared.errors import DomainError

_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "config/formal-capabilities-v1.json"
_REMOVED_CAPABILITIES = frozenset(
    {"FT-033", "FT-053", "FT-059", "FT-061", "FT-062", "FT-063"}
)

DataState = Literal["satisfied", "partial", "missing", "not_required"]
PermissionState = Literal["granted", "not_granted", "not_applicable"]


def _registry() -> tuple[dict[str, str], ...]:
    try:
        document = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DomainError("正式能力注册表无法读取") from exc
    raw_items = document.get("capabilities") if isinstance(document, dict) else None
    raw_removed = document.get("excluded_as_not_built") if isinstance(document, dict) else None
    if not isinstance(raw_items, list) or set(cast(list[object], raw_removed or [])) != _REMOVED_CAPABILITIES:
        raise DomainError("正式能力注册表边界无效")
    items: list[dict[str, str]] = []
    for raw in raw_items:
        if not isinstance(raw, dict) or any(not isinstance(value, str) for value in raw.values()):
            raise DomainError("正式能力注册表字段无效")
        item = cast(dict[str, str], raw)
        if set(item) != {
            "id",
            "role",
            "route",
            "title",
            "consumer",
            "data_gate",
            "permission_gate",
            "supplement",
        }:
            raise DomainError("正式能力注册表字段无效")
        items.append(item)
    identifiers = [item["id"] for item in items]
    if (
        len(items) != len(set(identifiers))
        or set(identifiers) & _REMOVED_CAPABILITIES
        or identifiers != sorted(identifiers)
    ):
        raise DomainError("正式能力注册表存在重复、越界或乱序")
    return tuple(items)


def _integer(inputs: dict[str, object], key: str) -> int:
    value = inputs.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DomainError(f"正式就绪输入 {key} 无效")
    return value


def _product_fact_readiness(inputs: dict[str, object]) -> list[dict[str, object]]:
    raw_products = inputs.get("product_fact_readiness")
    if not isinstance(raw_products, list):
        raise DomainError("正式商品事实就绪清单无效")
    products: list[dict[str, object]] = []
    for raw in raw_products:
        if not isinstance(raw, dict) or set(raw) != {
            "sku",
            "display_name",
            "current_facts",
            "missing_fields",
        }:
            raise DomainError("正式商品事实就绪条目无效")
        sku = raw.get("sku")
        display_name = raw.get("display_name")
        current_facts = raw.get("current_facts")
        missing_fields = raw.get("missing_fields")
        if (
            not isinstance(sku, str)
            or not sku.strip()
            or not isinstance(display_name, str)
            or not display_name.strip()
            or not isinstance(current_facts, dict)
            or any(
                not isinstance(key, str)
                or not key.strip()
                or not isinstance(value, str)
                or not value.strip()
                for key, value in current_facts.items()
            )
            or not isinstance(missing_fields, list)
            or any(
                not isinstance(value, str) or not value.strip()
                for value in missing_fields
            )
            or len(missing_fields) != len(set(cast(list[str], missing_fields)))
        ):
            raise DomainError("正式商品事实就绪字段无效")
        facts = [
            {"field": str(field), "value": str(value)}
            for field, value in sorted(current_facts.items())
        ]
        products.append(
            {
                "sku": sku.strip(),
                "display_name": display_name.strip(),
                "current_facts": facts,
                "missing_fields": sorted(cast(list[str], missing_fields)),
                "can_do": (
                    "可基于下列已确认字段解释这件商品的选择依据；每次任务只加载该 SKU 的事实。"
                    if facts
                    else "当前只能识别已登记商品身份，不能让它承担具体商品判断。"
                ),
                "cannot_promise": (
                    "未列入当前可用事实的属性、工艺、性能、功效、体验和品牌保证均不能承诺。"
                ),
            }
        )
    if len(products) != len({str(item["sku"]).casefold() for item in products}):
        raise DomainError("正式商品事实就绪清单含重复 SKU")
    return products


def _content_data_state(inputs: dict[str, object]) -> DataState:
    publication_ready = (
        bool(inputs.get("publication_confirmed"))
        and _integer(inputs, "publication_source_bound_items") > 1
        and _integer(inputs, "publication_brand_facts") > 0
        and _integer(inputs, "publication_expression_constraints") > 0
        and _integer(inputs, "publication_creative_methods") > 0
    )
    required = (
        publication_ready,
        _integer(inputs, "source_documents") > 0,
        _integer(inputs, "root_accounts") > 0,
        _integer(inputs, "platform_targets") > 0,
        _integer(inputs, "profile_accounts") > 0,
        _integer(inputs, "content_users") > 0,
    )
    if all(required):
        return "satisfied"
    return "partial" if any(required) else "missing"


def _data_state(gate: str, inputs: dict[str, object]) -> DataState:
    if gate in {"not_required", "tenant_readiness", "service_observation"}:
        return "not_required"
    if gate == "content_path":
        return _content_data_state(inputs)
    if gate == "product_catalog":
        has_products = _integer(inputs, "active_products") > 0
        has_approved_fields = _integer(inputs, "allowed_product_fact_fields") > 0
        if has_products and has_approved_fields:
            return "satisfied"
        return "partial" if has_products else "missing"
    if gate == "organization_media":
        return "satisfied" if _integer(inputs, "organization_media") > 0 else "missing"
    if gate == "dm01_path":
        parts = (
            _integer(inputs, "confirmed_stores") > 0,
            _integer(inputs, "display_users") > 0,
            _integer(inputs, "formal_inventory_snapshots") > 0,
        )
        if all(parts):
            return "satisfied"
        return "partial" if any(parts) else "missing"
    raise DomainError("正式能力注册表含未知资料门")


def _permission_state(
    gate: str,
    *,
    viewer_role: str,
    can_content: bool,
    can_display: bool,
) -> PermissionState:
    if gate == "public":
        return "granted"
    if gate == "authenticated":
        return "granted" if viewer_role in {"tenant_admin", "tenant_user", "ops"} else "not_applicable"
    if gate == "activation_token":
        return "not_applicable"
    if gate == "tenant_admin":
        return "granted" if viewer_role == "tenant_admin" else "not_granted"
    if gate == "tenant_user_content":
        return "granted" if viewer_role == "tenant_user" and can_content else "not_granted"
    if gate == "tenant_user_display":
        return "granted" if viewer_role == "tenant_user" and can_display else "not_granted"
    if gate == "ops":
        return "granted" if viewer_role == "ops" else "not_granted"
    raise DomainError("正式能力注册表含未知权限门")


def capability_matrix(
    inputs: dict[str, object],
    *,
    viewer_role: str,
    can_content: bool,
    can_display: bool,
    runtime_sha: str,
) -> dict[str, object]:
    observations = inputs.get("observed_capability_ids")
    if not isinstance(observations, list) or any(not isinstance(item, str) for item in observations):
        raise DomainError("正式能力实测观察无效")
    observed = frozenset(cast(list[str], observations))
    items = []
    for record in _registry():
        data_state = _data_state(record["data_gate"], inputs)
        permission_state = _permission_state(
            record["permission_gate"],
            viewer_role=viewer_role,
            can_content=can_content,
            can_display=can_display,
        )
        items.append(
            {
                "id": record["id"],
                "role": record["role"],
                "route": record["route"],
                "title": record["title"],
                "consumer": record["consumer"],
                "software_implemented": True,
                "data_state": data_state,
                "permission_state": permission_state,
                "formally_tested": record["id"] in observed,
                "supplement_href": record["supplement"],
            }
        )
    return {
        "registry_version": "tenant01-formal-capabilities-v1",
        "runtime_sha": runtime_sha,
        "schema_revision": str(inputs.get("schema_revision", "unknown")),
        "generated_at": str(inputs.get("evaluated_at", "")),
        "truth_sources": [
            "正式能力注册表",
            "当前租户 PostgreSQL 业务对象与权限",
            "同一候选 SHA 的追加式正式实测观察",
        ],
        "summary": {
            "implemented": sum(bool(item["software_implemented"]) for item in items),
            "not_built": len(_REMOVED_CAPABILITIES),
            "data_satisfied": sum(item["data_state"] in {"satisfied", "not_required"} for item in items),
            "permission_granted": sum(item["permission_state"] == "granted" for item in items),
            "formally_tested": sum(bool(item["formally_tested"]) for item in items),
        },
        "items": items,
    }


def guide_truth(inputs: dict[str, object]) -> dict[str, object]:
    """Human guidance whose counts and gaps come only from the live tenant query."""

    content_state = _content_data_state(inputs)
    return {
        "identity_model": [
            "笛语系统运维管理员：只负责最小租户开通、停用、恢复和运维审计。/ops 不是完整控制平面。",
            "笛语服饰租户管理员：维护组织、成员、发布账号、平台目标、账号画像和品牌资料。",
            "笛语服饰租户用户：只在本人获准的发布账号、平台、内容或陈列范围内工作。",
        ],
        "relationship": "自然人 → 工作资格 → 逻辑发布账号 → 平台和形式",
        "send_vs_generate": {
            "send": "发送只进行普通交流，不建立任务、运行或版本。",
            "generate": "生成内容才建立正式任务、运行和不可变版本。",
        },
        "administrator_steps": [
            "先建立或确认成员所属组织。",
            "建立逻辑发布账号，声明机构账号或个人 IP 的 ContentRole。",
            "为逻辑账号添加所需的平台与形式目标。",
            "确认五段画像 V1；后续修改保存为 V2，历史版本不会被覆盖。",
            "创建成员，填写允许同名的姓名或工作名，以及全系统唯一的登录用户名。",
            "只授予该组织可合法使用的发布账号和画像维护范围。",
            "把一次性 HTTPS 激活链接安全交给本人；密码至少 12 位。",
        ],
        "named_member_examples": [
            "笛语品控：使用已经建立的正式内容账号资格进入内容工作台。",
            "柯桥店阿丹：姓名或工作名允许与历史对象同名；应使用全系统唯一的中文登录用户名，例如“笛语柯桥店阿丹”。",
        ],
        "current_counts": {
            "source_documents": _integer(inputs, "all_source_documents"),
            "authorized_source_documents": _integer(inputs, "source_documents"),
            "template_documents": _integer(inputs, "template_documents"),
            "source_segments": _integer(inputs, "source_segments"),
            "publication_version": _integer(inputs, "publication_version"),
            "publication_items": _integer(inputs, "publication_items"),
            "publication_source_bound_items": _integer(
                inputs, "publication_source_bound_items"
            ),
            "publication_brand_facts": _integer(inputs, "publication_brand_facts"),
            "publication_expression_constraints": _integer(
                inputs, "publication_expression_constraints"
            ),
            "publication_creative_methods": _integer(
                inputs, "publication_creative_methods"
            ),
            "formal_users": _integer(inputs, "formal_users"),
            "content_users": _integer(inputs, "content_users"),
            "logical_accounts": _integer(inputs, "root_accounts"),
            "platform_targets": _integer(inputs, "platform_targets"),
            "profile_accounts": _integer(inputs, "profile_accounts"),
            "active_products": _integer(inputs, "active_products"),
            "allowed_product_fact_fields": _integer(inputs, "allowed_product_fact_fields"),
            "organization_media": _integer(inputs, "organization_media"),
            "product_media_products": _integer(inputs, "product_media_products"),
            "confirmed_stores": _integer(inputs, "confirmed_stores"),
            "formal_inventory_snapshots": _integer(inputs, "formal_inventory_snapshots"),
        },
        "content_path_state": content_state,
        "brand_context_summary": {
            "status": (
                "source_bound_confirmed"
                if content_state == "satisfied"
                else "needs_admin_confirmation"
            ),
            "message": (
                "新内容只读取当前已确认、来源绑定且适用于本题的最小品牌表达；不会加载 5,046 个原始 segment。"
                if content_state == "satisfied"
                else "来源资料已保存，但还需管理员确认同时覆盖品牌事实、表达边界和创作方法的来源绑定版本。"
            ),
        },
        "truth_boundaries": [
            "用户本轮现场陈述只作为本次任务的只读现实来源，不自动进入可复用品牌或商品事实。",
            "具体商品属性、工艺、性能、功效和机构保证必须来自已确认来源。",
            "系统生成、修改、复制和导出；采用与发布由用户完成，系统不自动发布。",
        ],
        "product_fact_readiness": _product_fact_readiness(inputs),
        "service_status_meanings": [
            {
                "state": "unknown",
                "meaning": "最近没有足够新鲜的真实观察，不能据此宣称服务已停机。",
            },
            {
                "state": "degraded",
                "meaning": "最近观察到限流或可恢复异常；核心服务仍可用，应保留输入并按页面提示重试。",
            },
            {
                "state": "unavailable",
                "meaning": "最近观察到生成依赖不可用；这不改变数据库与既有版本的健康状态。",
            },
        ],
        "common_errors": [
            {
                "code": "USERNAME_TAKEN",
                "meaning": "登录用户名已被使用；可保留姓名或工作名，并改用页面给出的可用中文登录名。",
            },
            {
                "code": "ACCOUNT_ACCESS_REQUIRED",
                "meaning": "本人尚无发布账号资格；请租户管理员在成员详情中补充。",
            },
            {
                "code": "PLATFORM_TARGET_REQUIRED",
                "meaning": "逻辑账号尚无可用平台与形式；请在发布账号中补充平台目标。",
            },
            {
                "code": "STORE_DATA_REQUIRED",
                "meaning": "当前无正式门店或库存；先补门店档案和本次真实库存，普通内容不受影响。",
            },
            {
                "code": "FACT_SOURCE_REQUIRED",
                "meaning": "具体商品或机构承诺缺少可信来源；补商品字段证据或改为本轮个人观察。",
            },
            {
                "code": "PROVIDER_STATUS_UNKNOWN",
                "meaning": "最近没有足够新鲜的生成服务观察；这不等于服务已经停机，可稍后重试并保留输入。",
            },
            {
                "code": "PRE_TASK_VALIDATION_FAILED",
                "meaning": "任务创建前校验失败；按页面动作补资料或权限，并向支持人员提供 trace_id。",
            },
            {
                "code": "PROVIDER_UNAVAILABLE",
                "meaning": "模型或网络暂不可用；输入会保留，仅在页面明确可重试时重试。",
            },
            {
                "code": "VERSION_PERSISTENCE_FAILED",
                "meaning": "版本保存失败；系统不会留下半版本，可凭 trace_id 定位。",
            },
        ],
        "data_missing": [
            {
                "id": "P4",
                "missing": _integer(inputs, "confirmed_stores") == 0,
                "message": "当前没有正式门店档案；可继续普通内容，门店事实内容需先补门店档案。",
                "supplement_href": "/tenant-admin?section=members",
            },
            {
                "id": "P5",
                "missing": _integer(inputs, "product_media_products") < 2,
                "message": "当前没有足够的正式商品图片/视频及商品绑定，暂不能生成商品视觉成品；普通文字内容仍可使用。",
                "supplement_href": "/tenant-admin?section=library",
            },
            {
                "id": "DM01",
                "missing": (
                    _integer(inputs, "confirmed_stores") == 0
                    or _integer(inputs, "formal_inventory_snapshots") == 0
                ),
                "message": "当前缺少正式门店档案和库存，纯文字陈列暂不可用。",
                "supplement_href": "/tenant-admin?section=members",
            },
        ],
    }
