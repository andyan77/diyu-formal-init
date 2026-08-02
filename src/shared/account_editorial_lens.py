from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import cast

from src.shared.types import (
    AccountExpression,
    BrandContextPacket,
    BrandContextPacketV2,
    ContentProduct,
)

ACCOUNT_EDITORIAL_LENS_V1_VERSION = "account-editorial-lens-v1"
ACCOUNT_EDITORIAL_LENS_V2_VERSION = "account-editorial-lens-v2"
ACCOUNT_EDITORIAL_LENS_V3_VERSION = "account-editorial-lens-v3"
ACCOUNT_EDITORIAL_LENS_VERSION = ACCOUNT_EDITORIAL_LENS_V3_VERSION
_LENS_PRODUCTS = frozenset({"brand_life_narrative", "local_response"})


@dataclass(frozen=True)
class AccountEditorialLensV1:
    """A frozen editorial relationship contract, never a reality-fact license.

    The source profile and confirmed publication projection remain the trusted
    provenance.  The service-owned fields below describe how those sources may
    influence a life or local-response story without copying profile prose or
    changing the user's subject into an apparel/product subject.
    """

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
    """Current per-unit editorial responsibility for demonstrable P3/P4 work.

    V1 froze provenance and the overall account relationship.  V2 also makes
    every Writer-owned visible unit responsible for a different part of the
    finished work.  This prevents a profile slogan or a generic conclusion
    from satisfying the relationship contract in every field at once.
    """

    title_responsibility: str
    natural_guide_responsibility: str
    body_responsibility: str
    release_caption_responsibility: str
    actuality_response_boundary: str
    series_progression_boundary: str


@dataclass(frozen=True)
class AccountEditorialLensV3(AccountEditorialLensV2):
    """Current confirmed profile inputs that must influence, never become, copy.

    V2 made each visible unit accountable but still gave every account the same
    generic editorial lens.  V3 freezes the four confirmed profile fields that
    distinguish one logical publishing identity from another.  They remain
    expression constraints, not brand facts or reality claims, and the Writer
    copy guard rejects their verbatim reuse in visible units.
    """

    identity_position_input: str
    authority_boundary_input: str
    audience_relationship_input: str
    content_territories_input: str


AccountEditorialLens = (
    AccountEditorialLensV1
    | AccountEditorialLensV2
    | AccountEditorialLensV3
)


def build_account_editorial_lens(
    *,
    primary_product: ContentProduct,
    account_expression: AccountExpression | None,
    brand_context_packet: BrandContextPacket | None,
) -> AccountEditorialLensV3 | None:
    """Build the one auditable editorial lens for new P3/P4 tasks.

    Legacy packets and incomplete draft identities keep their historical path;
    they are not silently upgraded to the current publication contract.
    """

    if primary_product not in _LENS_PRODUCTS:
        return None
    if (
        account_expression is None
        or account_expression.profile_id is None
        or account_expression.version is None
        or account_expression.is_draft
        or not isinstance(brand_context_packet, BrandContextPacketV2)
    ):
        return None
    return AccountEditorialLensV3(
        contract_version=ACCOUNT_EDITORIAL_LENS_VERSION,
        primary_product=primary_product,
        source_profile_id=str(account_expression.profile_id),
        source_profile_version=account_expression.version,
        publication_projection_id=brand_context_packet.publication_projection_id,
        publication_projection_version=brand_context_packet.publication_projection_version,
        publication_projection_digest=brand_context_packet.publication_projection_digest,
        brand_context_packet_digest=brand_context_packet.packet_digest,
        relationship_principle=(
            "以当前账号已确认的判断边界和受众关系回应具体处境；给出清楚观看回报，"
            "同时把最终判断留给受众。"
        ),
        topic_fidelity=(
            "用户本次题材始终是作品主语；题材没有商品、服饰或门店时，不为证明品牌关联"
            "另行引入这些对象。"
        ),
        fact_boundary=(
            "只使用服务端冻结事实；账号画像和发布方法只决定观察、判断与待人方式，"
            "不证明任何人生、职业、顾客、经营或使用经历。"
        ),
        viewer_value_requirement=(
            "围绕本次输入独有的变化、冲突或选择给出至少一个可辨认的具体判断；"
            "该判断不能无损替换到另一件生活琐事。"
        ),
        closure_boundary=(
            "收束回本次具体变化或选择，不把个别片段升级为放之四海皆准的人生道理，"
            "也不粘贴账号定义或品牌口号。"
        ),
        title_responsibility=(
            "只命名本次输入中可见的变化、冲突或选择，不抢先解释原因，也不把题材改成"
            "账号、品牌或商品介绍。"
        ),
        natural_guide_responsibility=(
            "用一句自然文字说明读完能看清的本题判断，不介绍文章结构、创作方法或账号定义。"
        ),
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
            "若存在冻结系列前情，本篇必须推进一个新的判断或受众动作；不能复述前篇结论，"
            "也不能只替换比喻、标题或互动句。"
        ),
        identity_position_input=account_expression.identity_position,
        authority_boundary_input=account_expression.authority_boundary,
        audience_relationship_input=account_expression.audience_relationship,
        content_territories_input=account_expression.content_territories,
    )


def account_editorial_lens_document(
    lens: AccountEditorialLens,
) -> dict[str, object]:
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


def account_editorial_lens_from_document(
    value: dict[str, object],
) -> AccountEditorialLens:
    """Parse current and historical frozen lens snapshots without upgrading."""

    version = value.get("contract_version")
    if version == ACCOUNT_EDITORIAL_LENS_VERSION:
        return AccountEditorialLensV3(**value)  # type: ignore[arg-type]
    if version == ACCOUNT_EDITORIAL_LENS_V2_VERSION:
        return AccountEditorialLensV2(**value)  # type: ignore[arg-type]
    if version == ACCOUNT_EDITORIAL_LENS_V1_VERSION:
        return AccountEditorialLensV1(**value)  # type: ignore[arg-type]
    raise TypeError("account editorial lens version is unsupported")
