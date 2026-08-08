from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import cast

from src.shared.types import (
    AccountExpression,
    BrandContextPacket,
    BrandContextPacketV3,
    ContentProduct,
)

ACCOUNT_EDITORIAL_LENS_V1_VERSION = "account-editorial-lens-v1"
ACCOUNT_EDITORIAL_LENS_V2_VERSION = "account-editorial-lens-v2"
ACCOUNT_EDITORIAL_LENS_V3_VERSION = "account-editorial-lens-v3"
ACCOUNT_EDITORIAL_LENS_V4_VERSION = "account-editorial-lens-v4"
ACCOUNT_EDITORIAL_LENS_VERSION = ACCOUNT_EDITORIAL_LENS_V4_VERSION
ACCOUNT_EDITORIAL_RESOLUTION_VERSION = "account-editorial-resolution-v1"

_LENS_PRODUCTS = frozenset(
    {
        "dressing_decision",
        "product_truth",
        "brand_life_narrative",
        "local_response",
        "visual_styling_story",
    }
)
LENS_PRODUCTS = _LENS_PRODUCTS


class AccountEditorialDegradedReason(str, Enum):
    UNSUPPORTED_CONTENT_PRODUCT = "unsupported_content_product"
    ACCOUNT_PROFILE_MISSING = "account_profile_missing"
    ACCOUNT_PROFILE_IDENTITY_INCOMPLETE = "account_profile_identity_incomplete"
    ACCOUNT_PROFILE_NOT_CONFIRMED = "account_profile_not_confirmed"
    BRAND_CONTEXT_INCOMPATIBLE = "brand_context_incompatible"


ACCOUNT_EDITORIAL_DEGRADED_REASONS: tuple[AccountEditorialDegradedReason, ...] = tuple(AccountEditorialDegradedReason)

_TOPIC_FIDELITY = "用户本次题材始终是作品主语；题材没有商品、服饰或门店时，不为证明品牌关联另行引入这些对象。"
_FACT_BOUNDARY = (
    "只使用服务端冻结事实；账号画像和发布方法只决定观察、判断与待人方式，不证明任何人生、职业、顾客、经营或使用经历。"
)
_VIEWER_VALUE_REQUIREMENT = (
    "围绕本次输入独有的变化、冲突或选择给出至少一个可辨认的具体判断；该判断不能无损替换到另一件生活琐事。"
)
_CLOSURE_BOUNDARY = "收束回本次具体变化或选择，不把个别片段升级为放之四海皆准的人生道理，也不粘贴账号定义或品牌口号。"


@dataclass(frozen=True)
class AccountEditorialLensV1:
    """A frozen editorial relationship contract, never a reality-fact license."""

    contract_version: str
    primary_product: ContentProduct
    source_profile_id: str
    source_profile_version: int
    publication_projection_id: str
    publication_projection_version: int
    publication_projection_digest: str
    brand_context_packet_digest: str
    relationship_principle: str
    topic_fidelity: str
    fact_boundary: str
    viewer_value_requirement: str
    closure_boundary: str


@dataclass(frozen=True)
class AccountEditorialLensV2(AccountEditorialLensV1):
    """Historical per-unit editorial responsibility for P3/P4 work."""

    title_responsibility: str
    natural_guide_responsibility: str
    body_responsibility: str
    release_caption_responsibility: str
    actuality_response_boundary: str
    series_progression_boundary: str


@dataclass(frozen=True)
class AccountEditorialLensV3(AccountEditorialLensV2):
    """Historical confirmed profile inputs; inputs constrain but never become copy."""

    identity_position_input: str
    authority_boundary_input: str
    audience_relationship_input: str
    content_territories_input: str


@dataclass(frozen=True)
class AccountEditorialLensV4(AccountEditorialLensV3):
    """P1-P5 lens with the four permitted account-semantic effects made explicit."""

    observation_angle: str
    judgment_order: str
    audience_relation: str
    closure_method: str


AccountEditorialLens = AccountEditorialLensV1 | AccountEditorialLensV2 | AccountEditorialLensV3 | AccountEditorialLensV4


@dataclass(frozen=True)
class ResolvedAccountEditorialPermissionV4:
    identity: str
    audience: str
    attention_order: str
    response_posture: str
    refusals: str
    allowed_stance: str
    source_profile_id: str | None
    source_profile_version: int | None


@dataclass(frozen=True)
class AccountEditorialResolutionV4:
    """The single account-semantic result shared by every new-task consumer."""

    applied: bool
    contract_version: str
    lens: AccountEditorialLensV4 | None
    editorial_permission: ResolvedAccountEditorialPermissionV4
    degraded_reasons: tuple[AccountEditorialDegradedReason, ...]
    source_refs: tuple[str, ...]
    source_digest: str


def resolve_account_editorial_context(
    *,
    primary_product: ContentProduct | str,
    account_expression: AccountExpression | None,
    brand_context_packet: BrandContextPacket | None,
    content_role_name: str = "",
    content_role_boundary: str = "",
    expression_constraints: tuple[str, ...] = (),
    creative_methods: tuple[str, ...] = (),
) -> AccountEditorialResolutionV4:
    """Resolve all five business gates once; unknown or incomplete input fails closed."""

    ordered_reasons = _degraded_reasons(primary_product, account_expression, brand_context_packet)
    source_refs = _account_editorial_source_refs(account_expression, brand_context_packet)
    source_digest = _account_editorial_source_digest(
        primary_product=primary_product,
        account_expression=account_expression,
        brand_context_packet=brand_context_packet,
        content_role_name=content_role_name,
        content_role_boundary=content_role_boundary,
        expression_constraints=expression_constraints,
        creative_methods=creative_methods,
    )
    if ordered_reasons:
        return AccountEditorialResolutionV4(
            applied=False,
            contract_version=ACCOUNT_EDITORIAL_RESOLUTION_VERSION,
            lens=None,
            editorial_permission=_degraded_permission(
                account_expression,
                content_role_boundary=content_role_boundary,
                expression_constraints=expression_constraints,
            ),
            degraded_reasons=ordered_reasons,
            source_refs=source_refs,
            source_digest=source_digest,
        )

    if account_expression is None or not isinstance(brand_context_packet, BrandContextPacketV3):
        raise AssertionError("account editorial gates passed without compatible sources")
    lens = _build_account_editorial_lens_v4(
        primary_product=cast(ContentProduct, primary_product),
        account_expression=account_expression,
        brand_context_packet=brand_context_packet,
    )
    return AccountEditorialResolutionV4(
        applied=True,
        contract_version=ACCOUNT_EDITORIAL_RESOLUTION_VERSION,
        lens=lens,
        editorial_permission=_permission_from_lens(
            lens,
            content_role_name=content_role_name,
            content_role_boundary=content_role_boundary,
            expression_constraints=expression_constraints,
            creative_methods=creative_methods,
        ),
        degraded_reasons=(),
        source_refs=source_refs,
        source_digest=source_digest,
    )


def _degraded_reasons(
    primary_product: ContentProduct | str,
    account_expression: AccountExpression | None,
    brand_context_packet: BrandContextPacket | None,
) -> tuple[AccountEditorialDegradedReason, ...]:
    reasons: list[AccountEditorialDegradedReason] = []
    if primary_product not in _LENS_PRODUCTS:
        reasons.append(AccountEditorialDegradedReason.UNSUPPORTED_CONTENT_PRODUCT)
    profile_missing = account_expression is None or not _has_consumable_profile(account_expression)
    if profile_missing:
        reasons.append(AccountEditorialDegradedReason.ACCOUNT_PROFILE_MISSING)
    elif account_expression is not None:
        identity_incomplete = (
            account_expression.profile_id is None
            or account_expression.version is None
            or account_expression.version < 1
            or not account_expression.identity_position.strip()
            or not account_expression.authority_boundary.strip()
            or not account_expression.audience_relationship.strip()
            or not account_expression.content_territories.strip()
        )
        if identity_incomplete:
            reasons.append(AccountEditorialDegradedReason.ACCOUNT_PROFILE_IDENTITY_INCOMPLETE)
        if account_expression.is_draft:
            reasons.append(AccountEditorialDegradedReason.ACCOUNT_PROFILE_NOT_CONFIRMED)
    if not _brand_context_compatible(brand_context_packet):
        reasons.append(AccountEditorialDegradedReason.BRAND_CONTEXT_INCOMPATIBLE)
    return tuple(reason for reason in ACCOUNT_EDITORIAL_DEGRADED_REASONS if reason in reasons)


def build_account_editorial_lens(
    *,
    primary_product: ContentProduct | str,
    account_expression: AccountExpression | None,
    brand_context_packet: BrandContextPacket | None,
    content_role_name: str = "",
    content_role_boundary: str = "",
    expression_constraints: tuple[str, ...] = (),
    creative_methods: tuple[str, ...] = (),
) -> AccountEditorialResolutionV4:
    """Compatibility name for callers; now returns the structured resolution, never ``None``."""

    return resolve_account_editorial_context(
        primary_product=primary_product,
        account_expression=account_expression,
        brand_context_packet=brand_context_packet,
        content_role_name=content_role_name,
        content_role_boundary=content_role_boundary,
        expression_constraints=expression_constraints,
        creative_methods=creative_methods,
    )


def _build_account_editorial_lens_v4(
    *,
    primary_product: ContentProduct,
    account_expression: AccountExpression,
    brand_context_packet: BrandContextPacketV3,
) -> AccountEditorialLensV4:
    return AccountEditorialLensV4(
        contract_version=ACCOUNT_EDITORIAL_LENS_VERSION,
        primary_product=primary_product,
        source_profile_id=str(account_expression.profile_id),
        source_profile_version=cast(int, account_expression.version),
        publication_projection_id=brand_context_packet.publication_projection_id,
        publication_projection_version=brand_context_packet.publication_projection_version,
        publication_projection_digest=brand_context_packet.publication_projection_digest,
        brand_context_packet_digest=brand_context_packet.packet_digest,
        relationship_principle=(
            "以当前账号已确认的判断边界和受众关系回应具体处境；给出清楚观看回报，同时把最终判断留给受众。"
        ),
        topic_fidelity=_TOPIC_FIDELITY,
        fact_boundary=_FACT_BOUNDARY,
        viewer_value_requirement=_VIEWER_VALUE_REQUIREMENT,
        closure_boundary=_CLOSURE_BOUNDARY,
        title_responsibility=(
            "只命名本次输入中可见的变化、冲突或选择，不抢先解释原因，也不把题材改成账号、品牌或商品介绍。"
        ),
        natural_guide_responsibility=("用一句自然文字说明读完能看清的本题判断，不介绍文章结构、创作方法或账号定义。"),
        body_responsibility=(
            "只写面向受众下一次观察或回应的建议、条件或问题：先指出可以停留的可见之处，"
            "再给一个有限选择，最后留下一个不依赖新增现实事实的动作；不得解释、诊断或"
            "代替现实主体说明其心理、需要、意图和原因，三步不得互相复述。"
        ),
        release_caption_responsibility=(
            "用一至两句回到本题的具体变化或选择；不重复正文结论，不粘贴口号，也不强制互动。"
        ),
        actuality_response_boundary=(
            "若存在服务端冻结的用户现实原句，只回应原句中直接可见的反差或选择；不得猜测、"
            "罗列或暗示对象变化、感受变化或事件发生的原因，也不得把单次片段概括成人类、"
            "生活或关系的一般规律。"
        ),
        series_progression_boundary=(
            "若存在冻结系列前情，本篇必须推进一个新的判断或受众动作；不能复述前篇结论，也不能只替换比喻、标题或互动句。"
        ),
        identity_position_input=account_expression.identity_position,
        authority_boundary_input=account_expression.authority_boundary,
        audience_relationship_input=account_expression.audience_relationship,
        content_territories_input=account_expression.content_territories,
        observation_angle=(
            f"观察入口受冻结内容领地约束：{account_expression.content_territories}；它只改变先看什么，不替换本题。"
        ),
        judgment_order=(
            f"先履行冻结身份定位所承担的判断职责：{account_expression.identity_position}；再完成当前产品中心任务。"
        ),
        audience_relation=(
            f"回应姿态遵守冻结受众关系：{account_expression.audience_relationship}；不得据此补写受众身份或经历。"
        ),
        closure_method=(f"收束不得越过冻结权威边界：{account_expression.authority_boundary}；只回到本题可观察的选择。"),
    )


def _permission_from_lens(
    lens: AccountEditorialLensV4,
    *,
    content_role_name: str = "",
    content_role_boundary: str = "",
    expression_constraints: tuple[str, ...] = (),
    creative_methods: tuple[str, ...] = (),
) -> ResolvedAccountEditorialPermissionV4:
    scoped_constraints = tuple(
        f"只在本题事实、来源与资源边界内影响怎样表达：{item}" for item in expression_constraints if item.strip()
    )
    scoped_methods = tuple(
        f"只在本题事实、来源与资源边界内组织非事实创作：{item}" for item in creative_methods if item.strip()
    )
    return ResolvedAccountEditorialPermissionV4(
        identity=(
            f"以{content_role_name}的已确认职责回应本题；{lens.judgment_order}"
            if content_role_name
            else lens.judgment_order
        ),
        audience=lens.audience_relation,
        attention_order="；".join((lens.observation_angle, *scoped_methods)),
        response_posture="；".join((lens.audience_relation, *scoped_constraints)),
        refusals="；".join(
            item
            for item in (
                content_role_boundary,
                lens.fact_boundary,
                lens.closure_method,
            )
            if item
        ),
        allowed_stance="；".join((lens.relationship_principle, lens.closure_method, *scoped_methods)),
        source_profile_id=lens.source_profile_id,
        source_profile_version=lens.source_profile_version,
    )


def _degraded_permission(
    account_expression: AccountExpression | None,
    *,
    content_role_boundary: str = "",
    expression_constraints: tuple[str, ...] = (),
) -> ResolvedAccountEditorialPermissionV4:
    return ResolvedAccountEditorialPermissionV4(
        identity="只以当前已授权发布账号回应本题，不把账号画像当作人物或经历。",
        audience="只面向本次输入的直接读者，不从缺失画像推断受众身份。",
        attention_order="先完成当前内容产品的中心任务，不用未确认画像改变题材。",
        response_posture="保持条件、建议或观察语态，把最终判断留给受众。",
        refusals="；".join(
            item
            for item in (
                content_role_boundary,
                "不补写账号、品牌、员工、顾客或组织的经历、事实、授权与能力。",
                *(item for item in expression_constraints if item.strip()),
            )
            if item
        ),
        allowed_stance="只形成不依赖缺失账号语义的一般观察或条件建议。",
        source_profile_id=(
            str(account_expression.profile_id)
            if account_expression is not None and account_expression.profile_id is not None
            else None
        ),
        source_profile_version=(account_expression.version if account_expression is not None else None),
    )


def _has_consumable_profile(expression: AccountExpression) -> bool:
    return any(
        value.strip()
        for value in (
            expression.identity_position,
            expression.authority_boundary,
            expression.audience_relationship,
            expression.content_territories,
            expression.default_production_conditions,
        )
    )


def _brand_context_compatible(packet: BrandContextPacket | None) -> bool:
    return (
        isinstance(packet, BrandContextPacketV3)
        and bool(packet.publication_projection_id)
        and packet.publication_projection_version >= 1
        and _is_sha256(packet.publication_projection_digest)
        and _is_sha256(packet.packet_digest)
    )


def _account_editorial_source_refs(
    expression: AccountExpression | None,
    packet: BrandContextPacket | None,
) -> tuple[str, ...]:
    refs: list[str] = []
    if expression is not None and expression.profile_id is not None and expression.version is not None:
        refs.append(f"account-profile:{expression.profile_id}:v{expression.version}")
    if isinstance(packet, BrandContextPacketV3) and packet.publication_projection_id:
        refs.append(
            f"publication-projection:{packet.publication_projection_id}:v{packet.publication_projection_version}"
        )
    return tuple(refs)


def _account_editorial_source_digest(
    *,
    primary_product: ContentProduct | str,
    account_expression: AccountExpression | None,
    brand_context_packet: BrandContextPacket | None,
    content_role_name: str,
    content_role_boundary: str,
    expression_constraints: tuple[str, ...],
    creative_methods: tuple[str, ...],
) -> str:
    expression_document = (
        {
            "profile_id": str(account_expression.profile_id) if account_expression.profile_id is not None else None,
            "version": account_expression.version,
            "identity_position": account_expression.identity_position,
            "authority_boundary": account_expression.authority_boundary,
            "audience_relationship": account_expression.audience_relationship,
            "content_territories": account_expression.content_territories,
            "default_production_conditions": account_expression.default_production_conditions,
            "is_draft": account_expression.is_draft,
        }
        if account_expression is not None
        else None
    )
    packet_document = (
        {
            "packet_version": brand_context_packet.packet_version,
            "packet_digest": brand_context_packet.packet_digest,
            "publication_projection_id": brand_context_packet.publication_projection_id,
            "publication_projection_version": brand_context_packet.publication_projection_version,
            "publication_projection_digest": brand_context_packet.publication_projection_digest,
        }
        if isinstance(brand_context_packet, BrandContextPacketV3)
        else None
    )
    return hashlib.sha256(
        json.dumps(
            {
                "primary_product": primary_product,
                "account_expression": expression_document,
                "brand_context_packet": packet_document,
                "content_role_name": content_role_name,
                "content_role_boundary": content_role_boundary,
                "expression_constraints": list(expression_constraints),
                "creative_methods": list(creative_methods),
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def account_editorial_lens_document(lens: AccountEditorialLens) -> dict[str, object]:
    return cast(dict[str, object], asdict(lens))


def account_editorial_lens_digest(lens: AccountEditorialLens) -> str:
    return hashlib.sha256(
        json.dumps(
            account_editorial_lens_document(lens),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def account_editorial_resolution_document(
    resolution: AccountEditorialResolutionV4,
) -> dict[str, object]:
    permission = resolution.editorial_permission
    return {
        "applied": resolution.applied,
        "contract_version": resolution.contract_version,
        "lens": (account_editorial_lens_document(resolution.lens) if resolution.lens is not None else None),
        "editorial_permission": {
            "identity": permission.identity,
            "audience": permission.audience,
            "attention_order": permission.attention_order,
            "response_posture": permission.response_posture,
            "refusals": permission.refusals,
            "allowed_stance": permission.allowed_stance,
            "source_profile_id": permission.source_profile_id,
            "source_profile_version": permission.source_profile_version,
        },
        "degraded_reasons": [reason.value for reason in resolution.degraded_reasons],
        "source_refs": list(resolution.source_refs),
        "source_digest": resolution.source_digest,
    }


def account_editorial_resolution_digest(resolution: AccountEditorialResolutionV4) -> str:
    return hashlib.sha256(
        json.dumps(
            account_editorial_resolution_document(resolution),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def account_editorial_resolution_from_document(value: object) -> AccountEditorialResolutionV4:
    if not isinstance(value, dict):
        raise TypeError("account editorial resolution is invalid")
    raw_permission = value.get("editorial_permission")
    raw_reasons = value.get("degraded_reasons")
    raw_refs = value.get("source_refs")
    if not isinstance(raw_permission, dict) or not isinstance(raw_reasons, list) or not isinstance(raw_refs, list):
        raise TypeError("account editorial resolution is invalid")
    lens_value = value.get("lens")
    lens = account_editorial_lens_from_document(lens_value) if isinstance(lens_value, dict) else None
    if lens is not None and not isinstance(lens, AccountEditorialLensV4):
        raise TypeError("account editorial resolution lens is not current")
    try:
        resolution = AccountEditorialResolutionV4(
            applied=_required_bool(value.get("applied")),
            contract_version=str(value["contract_version"]),
            lens=lens,
            editorial_permission=ResolvedAccountEditorialPermissionV4(
                identity=str(raw_permission["identity"]),
                audience=str(raw_permission["audience"]),
                attention_order=str(raw_permission["attention_order"]),
                response_posture=str(raw_permission["response_posture"]),
                refusals=str(raw_permission["refusals"]),
                allowed_stance=str(raw_permission["allowed_stance"]),
                source_profile_id=_optional_string(raw_permission.get("source_profile_id")),
                source_profile_version=_optional_positive_int(raw_permission.get("source_profile_version")),
            ),
            degraded_reasons=tuple(AccountEditorialDegradedReason(str(reason)) for reason in raw_reasons),
            source_refs=tuple(str(ref) for ref in raw_refs),
            source_digest=str(value["source_digest"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise TypeError("account editorial resolution is invalid") from exc
    assert_account_editorial_resolution(resolution)
    return resolution


def assert_account_editorial_resolution(resolution: AccountEditorialResolutionV4) -> None:
    permission = resolution.editorial_permission
    invalid = (
        resolution.contract_version != ACCOUNT_EDITORIAL_RESOLUTION_VERSION
        or not _is_sha256(resolution.source_digest)
        or any(not value for value in asdict(permission).values() if value is not None)
        or len(set(resolution.degraded_reasons)) != len(resolution.degraded_reasons)
        or tuple(reason for reason in ACCOUNT_EDITORIAL_DEGRADED_REASONS if reason in resolution.degraded_reasons)
        != resolution.degraded_reasons
        or (resolution.applied and (resolution.lens is None or resolution.degraded_reasons))
        or (not resolution.applied and (resolution.lens is not None or not resolution.degraded_reasons))
    )
    if invalid:
        raise TypeError("account editorial resolution is invalid")
    if resolution.lens is not None and (
        resolution.lens.contract_version != ACCOUNT_EDITORIAL_LENS_VERSION
        or permission.source_profile_id != resolution.lens.source_profile_id
        or permission.source_profile_version != resolution.lens.source_profile_version
    ):
        raise TypeError("account editorial resolution is invalid")


def account_editorial_lens_from_document(value: dict[str, object]) -> AccountEditorialLens:
    """Parse frozen lens snapshots without upgrading historical versions."""

    version = value.get("contract_version")
    if version == ACCOUNT_EDITORIAL_LENS_VERSION:
        return AccountEditorialLensV4(**value)  # type: ignore[arg-type]
    if version == ACCOUNT_EDITORIAL_LENS_V3_VERSION:
        return AccountEditorialLensV3(**value)  # type: ignore[arg-type]
    if version == ACCOUNT_EDITORIAL_LENS_V2_VERSION:
        return AccountEditorialLensV2(**value)  # type: ignore[arg-type]
    if version == ACCOUNT_EDITORIAL_LENS_V1_VERSION:
        return AccountEditorialLensV1(**value)  # type: ignore[arg-type]
    raise TypeError("account editorial lens version is unsupported")


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _required_bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise TypeError("account editorial resolution is invalid")
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise TypeError("account editorial resolution is invalid")
    return value


def _optional_positive_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or value < 1:
        raise TypeError("account editorial resolution is invalid")
    return value
