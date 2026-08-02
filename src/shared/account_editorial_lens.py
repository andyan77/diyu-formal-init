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

ACCOUNT_EDITORIAL_LENS_VERSION = "account-editorial-lens-v1"
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


def build_account_editorial_lens(
    *,
    primary_product: ContentProduct,
    account_expression: AccountExpression | None,
    brand_context_packet: BrandContextPacket | None,
) -> AccountEditorialLensV1 | None:
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
    return AccountEditorialLensV1(
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
    )


def account_editorial_lens_document(
    lens: AccountEditorialLensV1,
) -> dict[str, object]:
    return cast(dict[str, object], asdict(lens))


def account_editorial_lens_digest(lens: AccountEditorialLensV1) -> str:
    return hashlib.sha256(
        json.dumps(
            account_editorial_lens_document(lens),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()
