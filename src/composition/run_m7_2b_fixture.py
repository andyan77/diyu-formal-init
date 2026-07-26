from __future__ import annotations

import json
import os
import secrets
import time
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from src.gateway.api.settings import Settings
from src.infrastructure.production_auth import ProductionAuthRepository, TenantSession
from src.shared.errors import DomainError

_CONFIRMATION = "synthetic_business_fixture"
_CATALOG_VERSION = "content-expression-catalog-v1"
_STYLE_PRACTICAL = "CAT-STYLE-PERSONA-01"
_STYLE_FRIEND = "CAT-STYLE-PERSONA-02"
_STYLE_EMPATHY = "CAT-STYLE-PERSONA-05"
_STYLE_HUMOUR = "CAT-STYLE-PERSONA-06"
_FORM_SPEAK = "CAT-GENRE-SPEAK-01"
_FORM_DETAILS = "CAT-GENRE-SHOW-04"
_FORM_IMAGES = "CAT-GENRE-NOTE-02"

_HQ_PROFILE = {
    "identity_position": (
        "这是笛语服饰总部品牌内容运营的演示表达身份。在本次生产验收中，它从总部岗位位置"
        "提出品牌判断、解释商品边界和组织长期主题；它不冒充创始人、研发人员、门店店员、"
        "顾客或真实员工本人。"
    ),
    "authority_boundary": (
        "只使用已经确认的品牌表达基线、明确标记的演示商品事实和本轮冻结前情。可以说"
        "“我们主张、希望、建议、尊重”，但不把模拟组织、模拟种子、单店做法或候选资料写成"
        "真实经营经历；不编价格、库存、性能、设计动机、销量、顾客反馈或全国执行情况。"
    ),
    "audience_relationship": (
        "主要面对想让家庭成员各自舒服、又能自然呼应的穿衣组织者。与受众平等讨论现实选择，"
        "帮助看见取舍和成立条件，不制造焦虑、不说教、不催促购买。"
    ),
    "content_territories": (
        "持续讨论家庭穿衣问题、品牌对生活关系的当前立场、演示商品能够支持的专业取舍，"
        "以及用画面看见新的穿着可能。总部负责提出判断和方法，不冒充门店现场。"
    ),
    "default_production_conditions": (
        "默认一名创作者、一部手机、普通室内和现有演示商品；优先自然口播、持衣演示、"
        "局部特写、旁白、字幕和简单图卡，不安排顾客、儿童、模特或复杂场地。"
    ),
}

_STORE_PROFILE = {
    "identity_position": (
        "这是柯桥门店人物位置的演示表达身份。在本次生产验收中，它从一线工作者的近距离视角"
        "说当下理解、具体犹豫和小观察；它不是总部公告口，也不冒充任何真实店员或员工确认。"
    ),
    "authority_boundary": (
        "只使用本轮明确标成模拟的门店种子、当前演示商品事实和本系列冻结前情。没有来源时只说"
        "“我会怎么理解、我更愿意怎样建议”，不声称本店一直这样做、顾客经常这样问或全国门店"
        "已经执行；一家模拟门店的内容也不扩大成品牌政策。"
    ),
    "audience_relationship": (
        "主要面对来到门店前后仍想保留自己节奏的家庭和普通穿衣者，像一个在现场认真听人说话的"
        "熟人：给可执行选择，也给人不被催促的余地。"
    ),
    "content_territories": (
        "持续经营门店里的细小穿衣处境、家庭成员之间怎样保留舒服、商品在手边能看见的细节，"
        "以及一线工作中值得说清的小事；不把每件小事强行商品化、励志化或改成品牌宣言。"
    ),
    "default_production_conditions": (
        "默认一人、一部手机、普通室内或现有门店式空间和现有演示商品；可以对镜口播、持衣、"
        "拍衣架与局部特写、配旁白和字幕，不要求顾客、儿童、一家三口或额外模特出镜。"
    ),
}

_PRODUCTS: tuple[dict[str, object], ...] = (
    {
        "sku": "DIYU-CSPU-001",
        "display_name": "男童亮黄短袖（M7-2B演示商品）",
        "category": "男童短袖上衣",
        "colors": ["明亮黄色"],
        "material_or_structure": "",
        "silhouette": "",
        "observable_features": "候选视频画面可见：短袖上衣，明亮黄色。",
    },
    {
        "sku": "DIYU-CSPU-006",
        "display_name": "女童白色连衣裙（M7-2B演示商品）",
        "category": "女童连衣裙",
        "colors": ["白色或米白色"],
        "material_or_structure": "",
        "silhouette": "",
        "observable_features": "候选视频画面可见：女童连衣裙，白色或米白色。",
    },
    {
        "sku": "DIYU-CSPU-009",
        "display_name": "女童牛角扣学院外套（M7-2B演示商品）",
        "category": "女童中长款秋冬外套",
        "colors": [],
        "material_or_structure": "牛角扣、学院外套结构",
        "silhouette": "",
        "observable_features": "候选视频画面可见：中长款秋冬外套，带牛角扣和学院外套结构。",
    },
)


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"缺少 {name}")
    return value


def _response_json(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    expected: tuple[int, ...] = (200,),
    json_body: dict[str, Any] | None = None,
    form_body: dict[str, str] | None = None,
) -> Any:
    response = client.request(
        method,
        path,
        json=json_body,
        data=form_body,
        follow_redirects=False,
    )
    if response.status_code not in expected:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text[:500]
        raise RuntimeError(
            f"{method} {path} 返回 {response.status_code}: "
            f"{json.dumps(detail, ensure_ascii=False)}"
        )
    if response.status_code == 303:
        return {"location": response.headers.get("location", "")}
    return response.json()


def _find_named(items: list[dict[str, Any]], key: str, value: str) -> dict[str, Any] | None:
    return next((item for item in items if str(item.get(key) or "") == value), None)


def _ensure_organization(
    admin: httpx.Client,
    name: str,
    *,
    synthetic: bool,
) -> dict[str, Any]:
    organizations = _response_json(
        admin, "GET", "/api/v1/tenant-management/organizations"
    )
    existing = _find_named(organizations, "name", name)
    if existing is not None:
        return existing
    return cast(
        dict[str, Any],
        _response_json(
            admin,
            "POST",
            "/api/v1/tenant-management/organizations",
            expected=(201,),
            json_body={
                "name": name,
                "as_synthetic_business_fixture": synthetic,
            },
        ),
    )


def _ensure_user(
    admin: httpx.Client,
    *,
    display_name: str,
    username: str,
    organization_id: str,
) -> tuple[dict[str, Any], str]:
    operators = _response_json(
        admin, "GET", "/api/v1/tenant-management/operators"
    )
    existing = _find_named(operators, "username", username)
    if existing is None:
        created = _response_json(
            admin,
            "POST",
            "/api/v1/tenant-management/users",
            expected=(201,),
            json_body={
                "display_name": display_name,
                "username": username,
                "organization_id": organization_id,
                "account_id": None,
                "grants_tenant_management": False,
                "grants_material_maintenance": False,
                "grants_expression_profile_maintenance": False,
            },
        )
        existing = {
            "id": created["user_id"],
            "display_name": display_name,
            "username": username,
        }
        return existing, str(created["activation_link"])
    reset = _response_json(
        admin,
        "POST",
        f"/api/v1/tenant-management/users/{existing['id']}/reset",
    )
    return existing, str(reset["reset_link"])


def _ensure_account(
    admin: httpx.Client,
    *,
    name: str,
    role: str,
    boundary: str,
    operator_id: str,
    control_organization_id: str,
) -> dict[str, Any]:
    accounts = _response_json(
        admin, "GET", "/api/v1/tenant-management/publishing-accounts"
    )
    existing = _find_named(accounts, "name", name)
    if existing is not None:
        if existing.get("business_data_kind") != "synthetic_business_fixture":
            raise RuntimeError(f"同名账号 {name} 不是等深模拟作用域，拒绝复用")
        return existing
    return cast(
        dict[str, Any],
        _response_json(
            admin,
            "POST",
            "/api/v1/tenant-management/publishing-accounts",
            expected=(201,),
            json_body={
                "name": name,
                "channel": "抖音",
                "content_role_name": role,
                "voice_boundary": boundary,
                "operator_id": operator_id,
                "control_organization_id": control_organization_id,
                "operator_can_maintain_expression_profile": True,
                "as_synthetic_business_fixture": True,
            },
        ),
    )


def _ensure_carriers(
    admin: httpx.Client,
    *,
    account: dict[str, Any],
    operator_id: str,
) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    for channel in ("小红书", "微信视频号"):
        accounts = _response_json(
            admin, "GET", "/api/v1/tenant-management/publishing-accounts"
        )
        existing = next(
            (
                item
                for item in accounts
                if str(item.get("carrier_of_account_id") or "") == str(account["id"])
                and str(item.get("channel") or "") == channel
            ),
            None,
        )
        if existing is not None:
            if existing.get("business_data_kind") != "synthetic_business_fixture":
                raise RuntimeError(f"{channel} 载体不是等深模拟作用域，拒绝复用")
            created.append(existing)
            continue
        value = _response_json(
            admin,
            "POST",
            "/api/v1/tenant-management/platform-carriers",
            expected=(201,),
            json_body={
                "source_account_id": str(account["id"]),
                "name": f"{account['name']}·{channel}",
                "channel": channel,
                "operator_id": operator_id,
                "confirm_internal_carrier": True,
            },
        )
        created.append(value)
    return created


def _activate_and_login(
    base_url: str,
    activation_link: str,
    username: str,
) -> httpx.Client:
    password = secrets.token_urlsafe(24)
    client = httpx.Client(base_url=base_url, timeout=150.0)
    _response_json(
        client,
        "POST",
        activation_link,
        expected=(303,),
        form_body={"password": password},
    )
    _response_json(
        client,
        "POST",
        "/login",
        expected=(303,),
        form_body={"username": username, "password": password},
    )
    return client


def _save_profile(
    client: httpx.Client,
    profile: dict[str, str],
) -> dict[str, Any]:
    current = _response_json(
        client, "GET", "/api/v1/content/account-expression-profile"
    )
    if current.get("current") is not None:
        frozen = current["current"]
        if all(str(frozen.get(key) or "") == value for key, value in profile.items()):
            return cast(dict[str, Any], frozen)
    return cast(
        dict[str, Any],
        _response_json(
            client,
            "POST",
            "/api/v1/content/account-expression-profile/versions",
            expected=(201,),
            json_body=profile,
        ),
    )


def _save_products(admin: httpx.Client) -> list[dict[str, Any]]:
    current = {
        str(item["sku"]): item
        for item in _response_json(
            admin, "GET", "/api/v1/tenant-management/brand-products"
        )
    }
    saved: list[dict[str, Any]] = []
    for product in _PRODUCTS:
        existing = current.get(str(product["sku"]))
        if (
            existing is not None
            and existing.get("source_kind") == "synthetic_business_fixture"
        ):
            saved.append(existing)
            continue
        saved.append(
            _response_json(
                admin,
                "PUT",
                "/api/v1/tenant-management/brand-products",
                json_body={
                    **product,
                    "source_note": (
                        "M7-2B 等深模拟业务夹具；仅采用现有候选商品主档的"
                        "视频画面可观察项，不是品牌方真实在售确认"
                    ),
                    "applicability": (
                        "仅用于 M7-2B 生产路径演示；不证明真实在售、价格、库存、"
                        "性能、设计动机或销售结果"
                    ),
                    "confirm_as_current_brand_fact": True,
                    "as_synthetic_business_fixture": True,
                },
            )
        )
    return saved


def _direction(
    *,
    style: str,
    form: str,
    custom_text: str,
) -> dict[str, object]:
    return {
        "catalog_version": _CATALOG_VERSION,
        "selections": {"style": style, "form": form},
        "cleared_axes": [],
        "custom_text": custom_text,
        "body_related_opt_in": False,
    }


def _new_series(
    client: httpx.Client,
    *,
    title: str,
    premise: str,
) -> dict[str, Any]:
    current = _response_json(client, "GET", "/api/v1/content/series")
    existing = _find_named(current, "title", title)
    if existing is not None:
        return existing
    return cast(
        dict[str, Any],
        _response_json(
            client,
            "POST",
            "/api/v1/content/series",
            expected=(201,),
            json_body={"title": title, "premise": premise},
        ),
    )


def _generate(
    client: httpx.Client,
    *,
    seed: str,
    series_id: str,
    position: int | None = None,
    direction: dict[str, object] | None = None,
) -> dict[str, Any]:
    body: dict[str, object] = {
        "weak_seed": seed,
        "target": "douyin_video",
        "series_id": series_id,
        "use_personal_preferences": False,
    }
    if position is not None:
        body["series_position"] = position
    if direction is not None:
        body["creative_direction"] = direction
    result = _response_json(
        client,
        "POST",
        "/api/v1/content",
        json_body=body,
    )
    if result.get("kind") != "content":
        raise RuntimeError(f"种子没有形成内容成品：{result}")
    time.sleep(2.0)
    return cast(dict[str, Any], result)


def _revise(
    client: httpx.Client,
    artifact: dict[str, Any],
    instruction: str,
) -> dict[str, Any]:
    result = _response_json(
        client,
        "POST",
        f"/api/v1/tasks/{artifact['task_id']}/revisions",
        expected=(201,),
        json_body={
            "instruction": instruction,
            "target": "douyin_video",
            "source_target": "douyin_video",
        },
    )
    time.sleep(2.0)
    return cast(dict[str, Any], result)


def _task_version(
    client: httpx.Client,
    task_id: str,
    version: int | None = None,
    target: str | None = None,
) -> dict[str, Any]:
    target_query = "" if target is None else f"?target={target}"
    versions = _response_json(
        client,
        "GET",
        f"/api/v1/content/tasks/{task_id}/versions{target_query}",
    )
    if not isinstance(versions, list):
        raise RuntimeError(f"任务 {task_id} 的版本响应无效")
    selected = next(
        (
            item
            for item in versions
            if version is None or int(str(item.get("version") or "0")) == version
        ),
        None,
    )
    if not isinstance(selected, dict):
        expected = "当前版" if version is None else f"V{version}"
        raise RuntimeError(f"任务 {task_id} 缺少{expected}")
    return selected


def _existing_series_artifact(
    client: httpx.Client,
    series: dict[str, Any],
    position: int,
) -> dict[str, Any] | None:
    items = series.get("items")
    if not isinstance(items, list):
        return None
    item = next(
        (
            candidate
            for candidate in items
            if isinstance(candidate, dict)
            and int(str(candidate.get("position") or "0")) == position
        ),
        None,
    )
    if not isinstance(item, dict):
        return None
    return _task_version(client, str(item["task_id"]))


def _ensure_generated(
    client: httpx.Client,
    *,
    seed: str,
    series: dict[str, Any],
    position: int,
    direction: dict[str, object],
) -> dict[str, Any]:
    existing = _existing_series_artifact(client, series, position)
    if existing is not None:
        return existing
    return _generate(
        client,
        seed=seed,
        series_id=str(series["id"]),
        position=position,
        direction=direction,
    )


def _ensure_revision(
    client: httpx.Client,
    artifact: dict[str, Any],
    instruction: str,
    desired_version: int = 2,
) -> dict[str, Any]:
    versions = _response_json(
        client,
        "GET",
        f"/api/v1/content/tasks/{artifact['task_id']}/versions",
    )
    if isinstance(versions, list) and any(
        isinstance(item, dict)
        and int(str(item.get("version") or "0")) == desired_version
        for item in versions
    ):
        return _task_version(client, str(artifact["task_id"]), desired_version)
    return _revise(client, artifact, instruction)


def _reset_series_with_tasks(
    client: httpx.Client,
    series_id: str,
    task_ids: tuple[str, ...],
) -> dict[str, Any]:
    current = cast(
        dict[str, Any],
        _response_json(
            client,
            "POST",
            f"/api/v1/content/series/{series_id}/reset",
        ),
    )
    for position, task_id in enumerate(task_ids, start=1):
        current = cast(
            dict[str, Any],
            _response_json(
                client,
                "POST",
                f"/api/v1/content/series/{series_id}/items",
                json_body={"task_id": task_id, "position": position},
            ),
        )
    return current


def _recompile(
    client: httpx.Client,
    artifact: dict[str, Any],
    target: str,
) -> dict[str, Any]:
    result = _response_json(
        client,
        "POST",
        f"/api/v1/tasks/{artifact['task_id']}/revisions",
        expected=(201,),
        json_body={
            "instruction": (
                "另做这个平台的版本：保留核心判断、演示商品事实、账号身份、系列前情"
                "和主要受众价值，按目标平台实质重组标题、开头、内容结构、媒体组织、"
                "画面节奏，以及确有需要的封面字、标签、首评或FAQ。不要只替换平台名或标签。"
                "业务资料和成品均为演示，不得写成真实顾客、真实门店做法、真实穿着结果或"
                "真实在售事实；只使用一名创作者、已登记演示商品、普通室内、字卡和手机，"
                "平台图文也不新增家庭成员、顾客、儿童、模特或未登记道具。"
            ),
            "target": target,
            "source_target": "douyin_video",
        },
    )
    time.sleep(2.0)
    return cast(dict[str, Any], result)


def _ensure_recompiled(
    client: httpx.Client,
    artifact: dict[str, Any],
    target: str,
) -> dict[str, Any]:
    recent = _response_json(
        client,
        "GET",
        f"/api/v1/content/tasks?target={target}",
    )
    if not isinstance(recent, list):
        raise RuntimeError(f"{target} 成品列表响应无效")
    matching = [
        item
        for item in recent
        if isinstance(item, dict)
        and str(item.get("target") or "") == target
        and str(item.get("source_version_id") or "") == str(artifact["version_id"])
    ]
    if len(matching) > 1:
        raise RuntimeError(f"{target} 已有多个演示成品，拒绝隐式选择")
    if matching:
        return _task_version(client, str(matching[0]["task_id"]), target=target)
    return _recompile(client, artifact, target)


def _ensure_platform_revision(
    client: httpx.Client,
    artifact: dict[str, Any],
    target: str,
    instruction: str,
    desired_version: int = 2,
) -> dict[str, Any]:
    versions = _response_json(
        client,
        "GET",
        f"/api/v1/content/tasks/{artifact['task_id']}/versions?target={target}",
    )
    if isinstance(versions, list) and any(
        isinstance(item, dict)
        and int(str(item.get("version") or "0")) == desired_version
        for item in versions
    ):
        return _task_version(
            client,
            str(artifact["task_id"]),
            desired_version,
            target=target,
        )
    result = _response_json(
        client,
        "POST",
        f"/api/v1/tasks/{artifact['task_id']}/revisions",
        expected=(201,),
        json_body={
            "instruction": instruction,
            "target": target,
            "source_target": target,
        },
    )
    time.sleep(2.0)
    return cast(dict[str, Any], result)


def run() -> dict[str, object]:
    if _required("DIYU_M7_2B_EXECUTE") != _CONFIRMATION:
        raise RuntimeError("DIYU_M7_2B_EXECUTE 必须明确等于 synthetic_business_fixture")
    settings = Settings.model_validate({})
    if not settings.is_production or settings.generator_mode != "deepseek":
        raise RuntimeError("M7-2B 夹具只允许在正式 DeepSeek 运行模式执行")
    tenant_id = UUID(_required("DIYU_M7_2B_TENANT_ID"))
    manager_user_id = UUID(_required("DIYU_M7_2B_MANAGER_USER_ID"))
    public_url = os.environ.get("DIYU_PUBLIC_URL", "https://diyuai.cc").rstrip("/")
    hostname = urlsplit(public_url).hostname
    if hostname is None:
        raise RuntimeError("DIYU_PUBLIC_URL 无效")

    repository = ProductionAuthRepository(settings.app_database_url)
    manager = TenantSession(tenant_id, manager_user_id, "tenant-admin")
    repository.manager_scope(manager)
    session_token = repository.create_tenant_session(manager)
    admin = httpx.Client(base_url=public_url, timeout=150.0)
    admin.cookies.set("diyu_session", session_token, domain=hostname, path="/")
    hq_client: httpx.Client | None = None
    store_client: httpx.Client | None = None
    try:
        hq_org = _ensure_organization(
            admin, "笛语服饰管理组织", synthetic=False
        )
        _ensure_organization(admin, "浙江区域演示组织", synthetic=True)
        store_org = _ensure_organization(
            admin, "柯桥门店演示组织", synthetic=True
        )
        hq_user, hq_activation = _ensure_user(
            admin,
            display_name="M7-2B总部内容演示操作者（模拟）",
            username="m72b-hq-demo",
            organization_id=str(hq_org["id"]),
        )
        store_user, store_activation = _ensure_user(
            admin,
            display_name="M7-2B柯桥门店演示操作者（模拟）",
            username="m72b-keqiao-demo",
            organization_id=str(store_org["id"]),
        )
        hq_account = _ensure_account(
            admin,
            name="总部品牌内容运营演示账号",
            role="总部品牌内容运营演示身份",
            boundary=(
                "从总部岗位提出品牌当前立场、解释演示商品边界和组织长期内容；"
                "不冒充真实员工、门店现场、顾客经历或全国执行情况。"
            ),
            operator_id=str(hq_user["id"]),
            control_organization_id=str(hq_org["id"]),
        )
        store_account = _ensure_account(
            admin,
            name="柯桥门店人物演示账号",
            role="柯桥门店人物演示身份",
            boundary=(
                "从模拟的一线人物位置说具体理解、条件建议和小观察；"
                "不冒充真实店员，不把模拟种子写成真实经营事实或总部政策。"
            ),
            operator_id=str(store_user["id"]),
            control_organization_id=str(store_org["id"]),
        )
        hq_carriers = _ensure_carriers(
            admin, account=hq_account, operator_id=str(hq_user["id"])
        )
        store_carriers = _ensure_carriers(
            admin, account=store_account, operator_id=str(store_user["id"])
        )
        products = _save_products(admin)

        hq_client = _activate_and_login(
            public_url, hq_activation, str(hq_user["username"])
        )
        store_client = _activate_and_login(
            public_url, store_activation, str(store_user["username"])
        )
        hq_profile = _save_profile(hq_client, _HQ_PROFILE)
        store_profile = _save_profile(store_client, _STORE_PROFILE)

        hq_series = _new_series(
            hq_client,
            title="总部｜让选择保留余地（M7-2B演示）",
            premise=(
                "从总部位置连续讨论：品牌怎样尊重人的节奏、解释商品边界，"
                "并用现有演示商品让受众看见新的穿着可能。所有内容均为演示成品。"
            ),
        )
        store_series = _new_series(
            store_client,
            title="柯桥门店人物｜在现场留一点余地（M7-2B演示）",
            premise=(
                "从模拟门店人物位置连续讨论：怎样听见具体犹豫、给条件性建议，"
                "也保留一线工作中不必被商品化的小事。所有内容均为演示成品。"
            ),
        )

        h1_current = _ensure_generated(
            hq_client,
            seed=(
                "走进门店只想自己看看，这种沉默是不是也应该被尊重？"
                "请从总部品牌内容岗位形成当前立场，但不要写成全国门店已经执行的服务，"
                "不要编造被问过很多次、长期观察到或内部反复讨论；一人面对手机自然说。"
            ),
            series=hq_series,
            position=1,
            direction=_direction(
                style=_STYLE_EMPATHY,
                form=_FORM_SPEAK,
                custom_text="保留明确判断，但不要写成高声量品牌宣言。",
            ),
        )
        h1_v1 = _task_version(hq_client, str(h1_current["task_id"]), 1)
        h1_v2 = _ensure_revision(
            hq_client,
            h1_current,
            "判断保留，但不要写成品牌宣言，改成一人面对手机能自然说出的版本。",
        )
        h1 = _ensure_revision(
            hq_client,
            h1_v2,
            (
                "继续只改事实边界：保留“沉默应被尊重”的总部当前判断，但删除“你有没有过这种经历”、"
                "“在笛语的店里你可以”“我们都在、我们也懂”等会被听成现实服务已经发生的表述。"
                "只说品牌现在主张、希望和建议怎样理解这个假设处境；不冒充门店已经执行，仍是一人对手机"
                "自然说出的完整版本。"
            ),
            desired_version=3,
        )
        existing_h2 = _existing_series_artifact(hq_client, hq_series, 2)
        if existing_h2 is not None and any(
            marker in str(existing_h2.get("body") or "")
            for marker in (
                "它属于学院风格",
                "经典的闭合方式",
                "羊毛混纺",
                "纯聚酯",
                "展示厚度",
            )
        ):
            hq_series = _reset_series_with_tasks(
                hq_client,
                str(hq_series["id"]),
                (str(h1["task_id"]),),
            )
        h2_current = _ensure_generated(
            hq_client,
            seed=(
                "接着这个系列做下一篇。请解释演示商品 DIYU-CSPU-009："
                "已登记事实只有它是女童中长款秋冬外套，肉眼可见牛角扣和学院外套结构。"
                "讲清一个容易被误解的商品取舍：这些可见结构可以作为看外观结构的检查入口，"
                "但“学院外套结构”只是登记的结构名称，不能据此推断经典、学院风归属、适合人群、"
                "面料、厚薄、保暖、耐用、好打理、品质、设计动机、价格、库存或真实在售。"
                "不要举羊毛、聚酯、填充物等未登记例子，不捏面料、不上桌，只用一人持衣与"
                "牛角扣和整体结构的局部特写完成。"
            ),
            series=hq_series,
            position=2,
            direction=_direction(
                style=_STYLE_PRACTICAL,
                form=_FORM_DETAILS,
                custom_text="让商品新增理解、限制和成立边界都能直接看懂。",
            ),
        )
        h2 = h2_current
        h3_seed = (
            "接着这个系列做下一篇。只依据演示商品 DIYU-CSPU-001 肉眼可见的"
            "明亮黄色短袖上衣，以及 DIYU-CSPU-006 肉眼可见的白色或米白色连衣裙，"
            "让一名创作者在同一手机取景框里手持两件衣服做三组画面：先完整并列；再让白色"
            "连衣裙占画面主体、亮黄短袖只从侧边露出一小块颜色；最后交换主次，让亮黄短袖"
            "占主体、白色连衣裙只露局部。受众必须从画面直接看见：同一对衣服可以被组织成"
            "“完整并列、白色为主亮黄点一下、亮黄为主白色留一块”三种穿衣配色主次设想。"
            "主回报是只有看到三组画面才成立的造型组织可能，不给购买或穿着选择建议，也不"
            "解释商品，不声称哪组更好看、更适合谁、更有家庭感或已经形成真实穿着结果。"
            "不安排儿童、顾客或模特，不新增桌子、纸笔、衣架或其他道具。保留一点克制冷幽默。"
        )
        existing_h3 = _existing_series_artifact(hq_client, hq_series, 3)
        if (
            existing_h3 is not None
            and (
                "演示商品锚点：" not in str(existing_h3.get("body") or "")
                or "哪件更靠前" in str(existing_h3.get("outline") or "")
            )
        ):
            hq_series = _reset_series_with_tasks(
                hq_client,
                str(hq_series["id"]),
                (str(h1["task_id"]), str(h2["task_id"])),
            )
        h3 = _ensure_generated(
            hq_client,
            seed=h3_seed,
            series=hq_series,
            position=3,
            direction=_direction(
                style=_STYLE_HUMOUR,
                form=_FORM_IMAGES,
                custom_text="幽默意图保留，按品牌边界收窄成克制的冷幽默。",
            ),
        )

        existing_s1 = _existing_series_artifact(store_client, store_series, 1)
        if existing_s1 is not None and any(
            marker in str(existing_s1.get("body") or "")
            for marker in ("可能刚下班", "不想被推销", "我会先离他远一点")
        ):
            store_series = _reset_series_with_tasks(
                store_client,
                str(store_series["id"]),
                (),
            )
        s1_current = _ensure_generated(
            store_client,
            seed=(
                "走进门店只想自己看看，这种沉默是不是也应该被尊重？"
                "请从柯桥门店人物的模拟位置回应同一个假设问题。没有真实顾客、进店事件或本店做法，"
                "不要猜对方刚下班、怕推销或有任何具体经历，只表达：如果有人只想安静看看，"
                "我当前更愿意先留一点距离，等对方发出需要帮助的信号再开口。这是当前理解和建议，"
                "不是本店已执行服务；只用一名创作者面对手机口播，不用顾客、衣架或商品出镜。"
            ),
            series=store_series,
            position=1,
            direction=_direction(
                style=_STYLE_FRIEND,
                form=_FORM_SPEAK,
                custom_text="像在现场认真听人说话，但全篇保持假设，不照搬总部口径。",
            ),
        )
        s1_v1 = _task_version(store_client, str(s1_current["task_id"]), 1)
        s1_v2 = _ensure_revision(
            store_client,
            s1_current,
            (
                "判断保留，但改成一名创作者面对手机能自然说出的完整版本。不要安排顾客、衣架或"
                "商品出镜；不猜顾客经历，不写真实本店做法。开头直接用“如果有人只想安静看看”，"
                "保持门店人物近距离、像在认真听人的语气。"
            ),
            desired_version=2,
        )
        s1 = s1_v2
        existing_s2 = _existing_series_artifact(store_client, store_series, 2)
        if existing_s2 is not None and any(
            marker in str(existing_s2.get("body") or "")
            for marker in ("桌面", "白纸", "马克笔", "压住了", "放在一起看着舒服")
        ):
            store_series = _reset_series_with_tasks(
                store_client,
                str(store_series["id"]),
                (str(s1["task_id"]),),
            )
        s2_current = _ensure_generated(
            store_client,
            seed=(
                "接着这个系列做下一篇：一家三口拍合照，先统一颜色，还是先保留每个人"
                "舒服的穿法？结合演示商品 DIYU-CSPU-001 和 DIYU-CSPU-006 做成帮助选择的"
                "假设内容：如果这次更在意各自舒服，就先各自舒服，再只找一个颜色呼应点；"
                "如果这次明确更在意画面统一，就先约定一个共同颜色关系。不要声称哪种会更自然、"
                "更耐看、颜色会压住另一种或形成真实穿着结果。低成本验证只让一名创作者在同一"
                "手机取景框里手持两件演示商品，分别改变明亮黄色和白色或米白色在画面中的位置，"
                "再由拍摄者按本次目标决定；不需要顾客、儿童或一家三口出镜，不新增桌子、纸笔、"
                "字卡、衣架或其他道具。"
            ),
            series=store_series,
            position=2,
            direction=_direction(
                style=_STYLE_PRACTICAL,
                form=_FORM_DETAILS,
                custom_text="只用持衣和同一手机取景框完成，不声称这是本店真实案例。",
            ),
        )
        s2_v1 = _task_version(store_client, str(s2_current["task_id"]), 1)
        s2 = _ensure_revision(
            store_client,
            s2_current,
            (
                "保留帮助选择的条件、反转条件和低成本验证动作，但把它改成真正可成立的当前版："
                "不要声称舒服会让表情姿态更自然、某种颜色会压住另一种颜色、正式照片会更耐看，"
                "也不要判断搭配结果。所有家庭与拍照场景都明确作为假设；验证只比较两件演示商品"
                "肉眼可见的明亮黄色与白色或米白色在手机取景框里的面积，不外推真实穿着结果。"
                "只用一名创作者、两件演示商品和手机，不新增桌子、纸笔、顾客、儿童或一家三口出镜。"
            ),
            desired_version=2,
        )
        existing_s3 = _existing_series_artifact(store_client, store_series, 3)
        if (
            existing_s3 is not None
            and any(
                marker in str(existing_s3.get("body") or "")
                for marker in (
                    "其实每天都要擦",
                    "试衣镜",
                    "白天的时候，这里人来人往",
                    "顾客的脚步声",
                )
            )
        ):
            store_series = _reset_series_with_tasks(
                store_client,
                str(store_series["id"]),
                (str(s1["task_id"]), str(s2["task_id"])),
            )
        s3_current = _ensure_generated(
            store_client,
            seed=(
                "接着这个系列做下一篇。等深模拟门店生活种子：假设关店前有几分钟安静下来，"
                "一个门店人物可能会重新听见自己的节奏。请把它充分增益成完整的假设情境演示："
                "标题、导读、口播、画面和配文都不得声称今天、每天或任何真实门店已经发生过这件事，"
                "不补顾客、脚步声、衣架、窗外、问价、销售、白天发生过的事或真实员工经历。只写这个"
                "假设时刻本身：一名创作者、手机黑屏反光或空墙静镜头、自己的呼吸和停顿。"
                "不强行商品化、励志化、戏剧化或改成品牌宣言，不使用试衣镜、抹布或额外道具。"
            ),
            series=store_series,
            position=3,
            direction=_direction(
                style=_STYLE_EMPATHY,
                form=_FORM_SPEAK,
                custom_text="小事本身成立，不追加顾客故事、销售意义或鸡汤结论。",
            ),
        )
        s3 = s3_current

        hq_xiaohongshu = _ensure_platform_revision(
            hq_client,
            _ensure_recompiled(hq_client, h3, "xiaohongshu_graphic"),
            "xiaohongshu_graphic",
            (
                "自然修改成真正的小红书图文当前版：标题和正文开头不能沿用抖音源版；"
                "开头先说明读完这组图片能看见什么，再用首图、递进图序和完整正文重新组织。"
                "每张图承担不同信息，不把视频分镜改名为图序，不只替换平台名或标签。"
                "核心判断、演示商品事实、账号身份、系列前情和画面造型价值保持不变。"
            ),
        )
        hq_wechat = _ensure_platform_revision(
            hq_client,
            _ensure_recompiled(hq_client, h3, "wechat_channels_video"),
            "wechat_channels_video",
            (
                "继续自然修改视频号版：上一版标题和开头仍太像抖音，这次标题不要再使用"
                "“同一对衣服”或“三种配色主次”原句，开头先交代“手边只有一件亮黄短袖和一件"
                "白色连衣裙，怎样让被单独转发的人看懂这组三画面”。先展示第三组结果，再回到完整"
                "并列和白色为主的两组，最后收束三种画面关系，实质改变信息顺序、镜头节奏、封面字"
                "和收尾互动。商品事实、账号身份和画面造型价值不变，不机械截短。"
            ),
            desired_version=3,
        )
        store_xiaohongshu = _ensure_platform_revision(
            store_client,
            _ensure_recompiled(store_client, s1, "xiaohongshu_graphic"),
            "xiaohongshu_graphic",
            (
                "自然修改成真正的小红书图文当前版：标题和正文开头不能沿用抖音源版，改从"
                "“有些沉默不是拒绝”进入。用首图提出假设，后续图片分别承担留一点距离、"
                "等待帮助信号和这是当前建议而非本店做法；完整正文可独立阅读。只出现一名创作者"
                "和手机，不新增顾客、衣架、商品、桌子或纸笔，不猜任何人的真实经历。"
            ),
            desired_version=2,
        )
        store_wechat = _ensure_platform_revision(
            store_client,
            _ensure_recompiled(store_client, s1, "wechat_channels_video"),
            "wechat_channels_video",
            (
                "继续自然修改视频号版：上一版标题仍是“如果有人只想安静看看”，第一句话仍是"
                "抖音源版的问题，这次两处都不能沿用。标题从“开口前先停一秒”这个动作进入；"
                "开头先静默一秒，再直接说“我更愿意先别急着开口”，然后才交代这是面对假设处境"
                "的当前建议。重组封面字、判断顺序和收尾互动，使被单独转发的人也能看懂。"
                "只出现一名创作者和手机，不新增顾客、衣架、商品或真实本店做法。"
            ),
            desired_version=3,
        )
        hq_platforms = {
            "douyin": h3,
            "xiaohongshu": hq_xiaohongshu,
            "wechat_channels": hq_wechat,
        }
        store_platforms = {
            "douyin": s1,
            "xiaohongshu": store_xiaohongshu,
            "wechat_channels": store_wechat,
        }
        return {
            "fixture_kind": _CONFIRMATION,
            "evidence_semantics": {
                "production_path": "real",
                "database_and_rls": "real",
                "model": settings.deepseek_model,
                "business_materials": "synthetic",
                "artifacts": "demo",
            },
            "organizations": [
                hq_org,
                _find_named(
                    _response_json(
                        admin,
                        "GET",
                        "/api/v1/tenant-management/organizations",
                    ),
                    "name",
                    "浙江区域演示组织",
                ),
                store_org,
            ],
            "identities": {
                "headquarters": {
                    "user_id": hq_user["id"],
                    "username": hq_user["username"],
                    "account": hq_account,
                    "profile": hq_profile,
                    "carriers": hq_carriers,
                },
                "store": {
                    "user_id": store_user["id"],
                    "username": store_user["username"],
                    "account": store_account,
                    "profile": store_profile,
                    "carriers": store_carriers,
                },
            },
            "products": products,
            "series": {
                "headquarters": {
                    "series": _find_named(
                        _response_json(hq_client, "GET", "/api/v1/content/series"),
                        "title",
                        str(hq_series["title"]),
                    ),
                    "artifacts": {
                        "H1_V1": h1_v1,
                        "H1_V2": h1_v2,
                        "H1": h1,
                        "H2": h2,
                        "H3": h3,
                    },
                },
                "store": {
                    "series": _find_named(
                        _response_json(store_client, "GET", "/api/v1/content/series"),
                        "title",
                        str(store_series["title"]),
                    ),
                    "artifacts": {
                        "S1_V1": s1_v1,
                        "S1_V2": s1_v2,
                        "S1": s1,
                        "S2_V1": s2_v1,
                        "S2": s2,
                        "S3": s3,
                    },
                },
            },
            "platform_versions": {
                "headquarters": hq_platforms,
                "store": store_platforms,
            },
        }
    finally:
        if hq_client is not None:
            hq_client.close()
        if store_client is not None:
            store_client.close()
        admin.close()
        repository.revoke_tenant_session(session_token)


if __name__ == "__main__":
    try:
        print(json.dumps(run(), ensure_ascii=False, indent=2))
    except DomainError as exc:
        raise RuntimeError(str(exc)) from exc
