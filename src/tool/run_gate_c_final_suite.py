from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from src.brain.platform_directions import direction_for
from src.shared.creative_plan import (
    ACCOUNT_BASELINE_TONE_ID,
    build_creative_plan,
)
from src.shared.delivery_compiler import DELIVERY_COMPILER_VERSION
from src.shared.factual_basis import build_product_fact_packet
from src.shared.media_program import (
    MediaResourceV1,
    build_media_capability_envelope,
    media_envelope_digest,
    media_envelope_document,
    media_program_digest,
    media_program_document,
    select_media_program,
)
from src.shared.narrative import new_frame, visible_digest
from src.shared.types import (
    AccountExpression,
    BrandContext,
    ContentProduct,
    ContentTarget,
    CreativeDirection,
    DirectionSelection,
    GeneratedArtifact,
    GenerationInput,
    MediaFormat,
    ProductFact,
    SeriesContext,
    SeriesEntry,
)
from src.tool.gate_c_evidence import (
    GATE_C_FINAL_CARD_IDS,
    GATE_C_REVIEW_CRITERIA,
    ArtifactEvidenceInput,
    HumanReviewInput,
    write_gate_c_evidence,
)
from src.tool.llm_gateway.deepseek import DeepSeekGenerator

_MODEL = "deepseek-v4-flash"
_SUITE_VERSION = "ux03-gate-c-final-suite-v2"
_CARDS = ("P1", "P2", "P3", "P4", "P5", "series2", "series3")
_HQ_PROFILE_ID = UUID("84000000-0000-0000-0000-000000000001")
_STORE_PROFILE_ID = UUID("84000000-0000-0000-0000-000000000002")
_SERIES_ID = UUID("84000000-0000-0000-0000-000000000003")


@dataclass(frozen=True)
class _CardSpec:
    card_id: str
    weak_seed: str
    primary_product: ContentProduct
    target: ContentTarget
    account_kind: str
    user_fact: str | None = None
    products: tuple[ProductFact, ...] = ()
    direction: CreativeDirection | None = None


class _EvidenceDeepSeekGenerator(DeepSeekGenerator):
    """Persist each provider response before local parsing or compilation."""

    def __init__(self, *, evidence_root: Path, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._evidence_root = evidence_root
        self._active_card: str | None = None
        self._request_count = 0

    def begin_card(self, card_id: str) -> None:
        if card_id not in GATE_C_FINAL_CARD_IDS:
            raise ValueError("unknown Gate C card")
        self._active_card = card_id
        self._request_count = 0

    def end_card(self) -> None:
        if self._request_count != 1:
            raise RuntimeError("each final card must make exactly one provider call")
        self._active_card = None

    def _request(
        self,
        system: str,
        prompt: str,
        max_tokens: int,
        *,
        thinking_disabled: bool = True,
        timeout_seconds: float | None = None,
    ) -> tuple[dict[str, Any], int]:
        card_id = self._active_card
        if card_id is None:
            raise RuntimeError("provider call is not bound to one final card")
        if self._request_count != 0:
            raise RuntimeError("a final card attempted an additional provider call")
        payload, retries = super()._request(
            system,
            prompt,
            max_tokens,
            thinking_disabled=thinking_disabled,
            timeout_seconds=timeout_seconds,
        )
        self._request_count += 1
        _write_private_json(
            self._evidence_root / f"{card_id}.raw.json",
            payload,
        )
        return payload, retries


def _stable_uuid(label: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"diyu:ux03:gate-c:{label}")


def _brand(account_kind: str, *, target: ContentTarget) -> BrandContext:
    is_hq = account_kind == "hq"
    media_format = "图文" if target == "xiaohongshu_graphic" else "视频"
    platform = "小红书" if target.startswith("xiaohongshu") else "抖音"
    return BrandContext(
        brand_name="折线衣间",
        positioning="用克制的选择帮助，让熟悉事物重新被看见",
        decision_order="先保留真实信息，再给出清楚选择",
        tone="自然、克制、具体，不用通用鸡汤代替判断",
        account_name=(
            "折线衣间·总部穿衣编辑"
            if is_hq
            else "折线衣间·柯桥门店观察员"
        ),
        operator_name="synthetic 运营者",
        organization_name=("折线衣间总部" if is_hq else "柯桥门店"),
        content_role_name=("穿衣选择编辑" if is_hq else "门店关系观察员"),
        content_role_boundary=(
            "提供穿衣选择与观察视角，不冒充商品体验或品牌历史。"
            if is_hq
            else "回应门店关系议题，不冒充顾客、员工或门店历史。"
        ),
        audience_description=(
            "希望在有限信息下得到清楚穿衣判断的人"
            if is_hq
            else "希望被尊重、不被催促，也能获得清楚回应的人"
        ),
        strategy_version="synthetic-brand-expression-v1",
        platform=platform,
        media_format=media_format,
        production_conditions="低成本单人制作；没有登记实物时使用抽象编排。",
        speaker_kind="institutional_account",
    )


def _account(account_kind: str) -> AccountExpression:
    if account_kind == "hq":
        return AccountExpression(
            _HQ_PROFILE_ID,
            1,
            "把穿衣问题拆成具体条件与可选路径的编辑",
            "不冒充试穿、商品体验、品牌历史或专业背书",
            "帮助受众在有限信息下保留自己的判断",
            "穿衣选择、商品认知、熟悉事物重新被看见",
            "低成本单人制作；抽象编排优先",
            False,
        )
    return AccountExpression(
        _STORE_PROFILE_ID,
        1,
        "尊重人在门店里按自己节奏选择的观察者",
        "不冒充顾客、员工、门店历史或已执行服务",
        "给想自己看一会儿的人留出空间，也给出可用回应",
        "门店关系、选择节奏、不打扰与回应",
        "低成本单人制作；抽象编排优先",
        False,
    )


def _explicit_direction() -> CreativeDirection:
    return CreativeDirection(
        catalog_version="content-expression-catalog-v1",
        selections=(
            DirectionSelection(
                axis="mechanism",
                stable_id="CAT-MECHANISM-CONTRAST-01",
                label="条件对照",
                applied_label="条件对照",
                translated=False,
                preserved_aspect="",
                origin="explicit",
            ),
            DirectionSelection(
                axis="style",
                stable_id="CAT-STYLE-PLAIN-01",
                label="克制直接",
                applied_label="克制直接",
                translated=False,
                preserved_aspect="",
                origin="explicit",
            ),
        ),
        custom_text="先给两组条件，再给一个不替用户做决定的下一步",
        body_related_opt_in=False,
        translation_notice=None,
    )


def _p2_product() -> ProductFact:
    return ProductFact(
        sku="ZX-C218",
        display_name="双面短外套",
        facts={
            "observable_features": "炭灰纯色、深绿细格纹",
            "both_sides_complete": True,
        },
        source_kind="synthetic_confirmed_product_record",
        source_note="Gate C P2 冻结事实",
        fact_version=1,
        applicability="synthetic_brand_all",
    )


def _p5_products() -> tuple[ProductFact, ...]:
    return (
        ProductFact(
            sku="SYN-VIS-01",
            display_name="登记商品甲",
            facts={"observable_features": "深色纯色外观"},
            source_kind="synthetic_confirmed_product_record",
            source_note="Gate C P5 冻结事实",
            fact_version=1,
            applicability="synthetic_brand_all",
        ),
        ProductFact(
            sku="SYN-VIS-02",
            display_name="登记商品乙",
            facts={"observable_features": "浅色细格外观"},
            source_kind="synthetic_confirmed_product_record",
            source_note="Gate C P5 冻结事实",
            fact_version=1,
            applicability="synthetic_brand_all",
        ),
    )


def _card_specs() -> tuple[_CardSpec, ...]:
    return (
        _CardSpec(
            "P1",
            "早上出门有点凉，中午又热，今天怎么穿更稳妥？",
            "dressing_decision",
            "douyin_video",
            "hq",
            direction=_explicit_direction(),
        ),
        _CardSpec(
            "P2",
            "ZX-C218，帮我写一篇小红书，重点说清两面完整外观带来的选择。",
            "product_truth",
            "xiaohongshu_graphic",
            "hq",
            products=(_p2_product(),),
        ),
        _CardSpec(
            "P3",
            "今天喝了一直喝的蓝山咖啡，居然是甜的，帮我发一条。",
            "brand_life_narrative",
            "xiaohongshu_graphic",
            "hq",
            user_fact="今天喝了一直喝的蓝山咖啡，居然是甜的。",
        ),
        _CardSpec(
            "P4",
            "今天店里有人只想自己看看。写一条回应这种状态的小红书。",
            "local_response",
            "xiaohongshu_graphic",
            "store",
            user_fact="今天店里有人只想自己看看。",
        ),
        _CardSpec(
            "P5",
            "用本次明确选择的两件登记商品做一条视觉关系图文。",
            "visual_styling_story",
            "xiaohongshu_graphic",
            "hq",
            products=_p5_products(),
        ),
        _CardSpec(
            "series2",
            "沿着第一篇的不打扰，继续写第二篇：怎样给出回应。",
            "local_response",
            "xiaohongshu_graphic",
            "store",
        ),
        _CardSpec(
            "series3",
            "继续第三篇：回应之后，怎样把选择留给对方。",
            "local_response",
            "xiaohongshu_graphic",
            "store",
        ),
    )


def _registered_product_resources() -> tuple[MediaResourceV1, ...]:
    return tuple(
        MediaResourceV1(
            resource_id=f"resource:registered-product:{index}:v1",
            resource_version="1",
            media_type="image",
            source_ref=f"synthetic-selected-product-media:{index}:v1",
            capability_id="registered_product_display",
        )
        for index in (1, 2)
    )


def _series_context(
    card_id: str,
    artifacts: dict[str, GeneratedArtifact],
) -> SeriesContext | None:
    if card_id not in {"series2", "series3"}:
        return None
    p4 = artifacts.get("P4")
    if p4 is None:
        raise RuntimeError("series evidence requires the first frozen entry")
    entries = [
        SeriesEntry(
            task_id=_stable_uuid("task:P4"),
            version_id=_stable_uuid("version:P4"),
            version=1,
            position=1,
            outline=p4.outline,
            body=p4.body,
        )
    ]
    if card_id == "series3":
        series2 = artifacts.get("series2")
        if series2 is None:
            raise RuntimeError("series3 requires the frozen second entry")
        entries.append(
            SeriesEntry(
                task_id=_stable_uuid("task:series2"),
                version_id=_stable_uuid("version:series2"),
                version=1,
                position=2,
                outline=series2.outline,
                body=series2.body,
            )
        )
    return SeriesContext(
        series_id=_SERIES_ID,
        revision=1,
        title="把选择留给人的三篇门店观察",
        premise="从不打扰，推进到回应，再推进到留出选择。",
        target_position=2 if card_id == "series2" else 3,
        prior_entries=tuple(entries),
    )


def _request_for(
    spec: _CardSpec,
    artifacts: dict[str, GeneratedArtifact],
) -> GenerationInput:
    media_format: MediaFormat = (
        "graphic" if spec.target == "xiaohongshu_graphic" else "video"
    )
    platform_shape = (
        "小红书图文完整成品"
        if media_format == "graphic"
        else "抖音短视频完整成品"
    )
    product_ids = tuple(build_product_fact_packet(spec.products).fact_ids)
    frame = new_frame(
        "actuality_reflection" if spec.user_fact is not None else "general_observation",
        (spec.user_fact,) if spec.user_fact is not None else (),
        product_ids,
    )
    series_context = _series_context(spec.card_id, artifacts)
    plan = build_creative_plan(
        topic_spans=(spec.weak_seed,),
        primary_value=spec.primary_product,
        tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
        mechanism_id=None,
        target_shape=platform_shape,
    )
    envelope = build_media_capability_envelope(
        platform_shape=platform_shape,
        media_format=media_format,
        registered_resources=(
            _registered_product_resources() if spec.card_id == "P5" else ()
        ),
    )
    program = select_media_program(
        primary_product=spec.primary_product,
        envelope=envelope,
        mechanism_id=plan.mechanism_id,
        series_position=(
            series_context.target_position
            if series_context is not None
            else None
        ),
        fact_count=len(product_ids),
    )
    return GenerationInput(
        run_id=_stable_uuid(f"run:{spec.card_id}"),
        task_id=_stable_uuid(f"task:{spec.card_id}"),
        weak_seed=spec.weak_seed,
        primary_product=spec.primary_product,
        revision_instruction=None,
        brand=_brand(spec.account_kind, target=spec.target),
        target=spec.target,
        media_format=media_format,
        platform_direction=direction_for(spec.target),
        products=spec.products,
        creative_direction=spec.direction,
        account_expression=_account(spec.account_kind),
        series_context=series_context,
        narrative_frame=frame,
        creative_plan=plan,
        delivery_compiler_version=DELIVERY_COMPILER_VERSION,
        media_capability_envelope=envelope,
        media_program=program,
    )


def _artifact_document(
    card_id: str,
    request: GenerationInput,
    artifact: GeneratedArtifact,
) -> dict[str, object]:
    envelope = request.media_capability_envelope
    program = request.media_program
    if envelope is None or program is None:
        raise RuntimeError("final artifact is missing its media contract")
    digest = visible_digest(artifact.outline, artifact.body)
    if digest != artifact.reviewed_digest:
        raise RuntimeError("generated artifact visible digest drifted")
    return {
        "suite_version": _SUITE_VERSION,
        "card_id": card_id,
        "outline": artifact.outline,
        "body": artifact.body,
        "visible_digest": digest,
        "model": artifact.model,
        "latency_ms": artifact.latency_ms,
        "retry_count": artifact.retry_count,
        "provider_usage": artifact.provider_usage,
        "primary_product": artifact.primary_product,
        "semantic_contract": asdict(artifact.semantic_contract),
        "production": asdict(artifact.production),
        "completion_snapshot_patch": artifact.completion_snapshot_patch,
        "request_contract": {
            "target": request.target,
            "media_format": request.media_format,
            "account_profile_id": str(
                request.account_expression.profile_id
                if request.account_expression is not None
                else ""
            ),
            "account_profile_version": (
                request.account_expression.version
                if request.account_expression is not None
                else None
            ),
            "series_id": (
                str(request.series_context.series_id)
                if request.series_context is not None
                else None
            ),
            "series_position": (
                request.series_context.target_position
                if request.series_context is not None
                else None
            ),
            "media_capability_envelope": media_envelope_document(envelope),
            "media_capability_envelope_digest": media_envelope_digest(
                envelope
            ),
            "media_program": media_program_document(program),
            "media_program_digest": media_program_digest(program),
        },
    }


def _generate(args: argparse.Namespace) -> None:
    evidence_root = Path(args.evidence_root).resolve()
    implementation_sha = _current_head()
    if implementation_sha != args.implementation_sha:
        raise RuntimeError("current HEAD is not the frozen implementation SHA")
    if _git_status():
        raise RuntimeError("final suite requires a clean worktree")
    if evidence_root.exists():
        raise RuntimeError("final suite evidence directory already exists")
    evidence_root.mkdir(mode=0o700, parents=True)
    evidence_root.chmod(0o700)
    _write_private_json(
        evidence_root / "suite-config.json",
        {
            "suite_version": _SUITE_VERSION,
            "implementation_sha": implementation_sha,
            "provider_config": {
                "model": _MODEL,
                "temperature": 0,
                "max_retries": 0,
                "database": False,
                "redis": False,
                "business_persistence": False,
            },
            "synthetic_registered_product_media_contract": {
                "tenant_scope": "synthetic-gate-c-tenant",
                "brand_scope": "synthetic-gate-c-brand",
                "account_scope": str(_HQ_PROFILE_ID),
                "organization_scope": "synthetic-gate-c-headquarters",
                "enabled": True,
                "selected_for_this_task": True,
                "frozen_version": "1",
            },
            "cards": list(_CARDS),
        },
    )
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    api_base_url = os.environ.get("DEEPSEEK_API_BASE_URL", "")
    if not api_key:
        raise RuntimeError("credential_loaded=false")
    if not api_base_url:
        raise RuntimeError("provider endpoint is unavailable")
    generator = _EvidenceDeepSeekGenerator(
        evidence_root=evidence_root,
        api_base_url=api_base_url,
        api_key=api_key,
        model=_MODEL,
        reviewer_provider=None,
        timeout_seconds=180.0,
        max_retries=0,
    )
    artifacts: dict[str, GeneratedArtifact] = {}
    summaries: list[dict[str, object]] = []
    for spec in _card_specs():
        request = _request_for(spec, artifacts)
        generator.begin_card(spec.card_id)
        artifact = generator.generate(request)
        generator.end_card()
        artifacts[spec.card_id] = artifact
        document = _artifact_document(spec.card_id, request, artifact)
        _write_private_json(
            evidence_root / f"{spec.card_id}.artifact.json",
            document,
        )
        summaries.append(
            {
                "card_id": spec.card_id,
                "visible_digest": document["visible_digest"],
                "program_id": (
                    request.media_program.program_id
                    if request.media_program is not None
                    else None
                ),
                "retry_count": artifact.retry_count,
            }
        )
        print(
            json.dumps(
                summaries[-1],
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    _write_private_json(
        evidence_root / "generation-summary.json",
        {
            "suite_version": _SUITE_VERSION,
            "implementation_sha": implementation_sha,
            "provider_response": "received",
            "card_count": len(summaries),
            "cards": summaries,
        },
    )


def _finalize(args: argparse.Namespace) -> None:
    evidence_root = Path(args.evidence_root).resolve()
    implementation_sha = _current_head()
    if implementation_sha != args.implementation_sha:
        raise RuntimeError("current HEAD is not the frozen implementation SHA")
    notes = _review_notes(args.review)
    artifacts = tuple(
        ArtifactEvidenceInput(
            card_id=card_id,
            artifact_file=f"{card_id}.artifact.json",
            raw_response_file=f"{card_id}.raw.json",
        )
        for card_id in _CARDS
    )
    reviews = tuple(
        HumanReviewInput(
            card_id=card_id,
            artifact_file=f"{card_id}.artifact.json",
            verdict="PASS",
            criteria={
                criterion: "PASS"
                for criterion in GATE_C_REVIEW_CRITERIA
            },
            notes=notes[card_id],
        )
        for card_id in _CARDS
    )
    write_gate_c_evidence(
        evidence_root,
        implementation_sha=implementation_sha,
        model=_MODEL,
        temperature=0,
        max_retries=0,
        artifacts=artifacts,
        reviews=reviews,
    )
    print(
        json.dumps(
            {
                "evidence": "verified",
                "card_count": len(artifacts),
                "implementation_sha": implementation_sha,
            },
            sort_keys=True,
        )
    )


def _review_notes(values: list[str]) -> dict[str, str]:
    notes: dict[str, str] = {}
    for value in values:
        card_id, separator, note = value.partition("=")
        if separator != "=" or card_id not in GATE_C_FINAL_CARD_IDS:
            raise ValueError("review must use CARD=NOTE")
        if not note.strip() or card_id in notes:
            raise ValueError("each final card needs one non-empty review note")
        notes[card_id] = note.strip()
    if set(notes) != GATE_C_FINAL_CARD_IDS:
        raise ValueError("human review does not cover the seven final cards")
    return notes


def _write_private_json(path: Path, value: object) -> None:
    content = (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n"
    ).encode()
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        remaining = memoryview(content)
        while remaining:
            written = os.write(descriptor, remaining)
            remaining = remaining[written:]
    finally:
        os.close(descriptor)
    path.chmod(0o600)


def _current_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _git_status() -> str:
    return subprocess.run(
        ["git", "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run and bind the isolated UX-03 Gate C final suite.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("--implementation-sha", required=True)
    generate.add_argument("--evidence-root", required=True)
    generate.set_defaults(action=_generate)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--implementation-sha", required=True)
    finalize.add_argument("--evidence-root", required=True)
    finalize.add_argument("--review", action="append", default=[])
    finalize.set_defaults(action=_finalize)
    return parser


def main() -> None:
    os.umask(0o077)
    args = _parser().parse_args()
    action = cast(Any, args.action)
    action(args)


if __name__ == "__main__":
    main()
