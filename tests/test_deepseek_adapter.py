from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, cast
from uuid import UUID

import httpx
import pytest

from src.brain.platform_directions import direction_for
from src.ports.reviewer_provider import (
    ReviewerProvider,
    ReviewerProviderResult,
)
from src.shared.clause_license import (
    CLAUSE_LICENSE_REVIEW_VERSION,
    CLAUSE_LICENSE_TOOL_NAME,
    ClauseLicenseV1,
    build_unit_clause_license_policies_v1,
    materialize_clause_licenses_v1,
    unsupported_quote_candidates_v1,
)
from src.shared.closed_review import (
    CLOSED_REVIEW_TOOL_NAME,
    CLOSED_REVIEW_VERSION,
    build_closed_review_questions,
)
from src.shared.creative_kernel import (
    KERNEL_VERSION,
    OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM_V2,
    CreativeKernelV1,
    build_kernel_skeleton,
    compiler_owned_unit_texts,
    parse_writer_kernel,
    select_kernel_program,
)
from src.shared.creative_plan import (
    ACCOUNT_BASELINE_TONE_ID,
    LEGACY_PLAN_VERSION,
    PLAN_VERSION,
    build_creative_plan,
    creative_plan_document,
    creative_plan_from_document,
)
from src.shared.delivery_compiler import (
    DUAL_TRACK_DELIVERY_COMPILER_VERSION,
)
from src.shared.errors import GenerationFailed
from src.shared.factual_basis import (
    brand_fact_records,
    build_product_fact_packet,
    product_fact_records,
    select_product_fact_block_ids,
)
from src.shared.narrative import (
    NarrativeFrame,
    NarrativeIssue,
    NarrativeMode,
    new_frame,
    user_fact_candidates,
    visible_digest,
)
from src.shared.review_evidence import (
    REVIEW_EVIDENCE_V2_VERSION,
    build_clause_contexts_v2,
    unit_contracts_v2,
)
from src.shared.types import (
    ActiveAsset,
    BrandContext,
    ConversationInput,
    ConversationTurn,
    GenerationInput,
    GraphicProductionBundle,
    ProductFact,
    RoutingInput,
)
from src.tool.llm_gateway.deepseek import BoundaryContext, DeepSeekGenerator


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeClient:
    responses: list[FakeResponse] = []
    requests: list[dict[str, object]] = []

    def __init__(self, **_: object) -> None:
        pass

    def __enter__(self) -> FakeClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def post(self, *_: object, **kwargs: object) -> FakeResponse:
        self.requests.append(kwargs)
        return self.responses.pop(0)


def test_json_content_accepts_only_unmatched_trailing_closers() -> None:
    valid = '{"kind":"ready","message":"可以开始"}'
    duplicated_closers = f'{valid}"}}"'

    assert json.loads(DeepSeekGenerator._json_content(duplicated_closers)) == {
        "kind": "ready",
        "message": "可以开始",
    }
    for unsafe in (
        f'{valid}{{"kind":"chat"}}',
        f"{valid}ignored",
        '{"kind":"ready",',
    ):
        with pytest.raises(json.JSONDecodeError):
            json.loads(DeepSeekGenerator._json_content(unsafe))


class FakeReviewerProvider(ReviewerProvider):
    @property
    def provider_name(self) -> str:
        return "test"

    @property
    def model_name(self) -> str:
        return "deepseek-test"

    def review(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        licenses: tuple[ClauseLicenseV1, ...],
        timeout_seconds: float,
    ) -> ReviewerProviderResult:
        del timeout_seconds
        response = FakeClient.responses.pop(0)
        FakeClient.requests.append(
            {
                "json": {
                    "model": self.model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                }
            }
        )
        if response.status_code >= 400:
            raise GenerationFailed("Reviewer 模型服务拒绝当前请求")
        payload = response.json()
        try:
            reviews = DeepSeekGenerator._strict_license_review_answers(
                payload,
                licenses=licenses,
            )
        except (
            KeyError,
            IndexError,
            TypeError,
            json.JSONDecodeError,
        ) as exc:
            raise GenerationFailed("Reviewer 许可证据不完整") from exc
        return ReviewerProviderResult(
            reviews=reviews,
            raw_payload=payload,
            retry_count=0,
        )


@pytest.fixture(autouse=True)
def _fake_client(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeClient.responses = []
    FakeClient.requests = []
    monkeypatch.setattr(httpx, "Client", FakeClient)


def _generator(*, max_retries: int = 0) -> DeepSeekGenerator:
    return DeepSeekGenerator(
        "https://example.invalid",
        "test-key",
        "deepseek-test",
        reviewer_provider=FakeReviewerProvider(),
        max_retries=max_retries,
    )


def _brand() -> BrandContext:
    return BrandContext(
        brand_name="笛语服饰",
        positioning="尊重每个人独立成立，也看见关系里的自然呼应",
        decision_order="先尊重差异，再讨论关系",
        tone="真实、克制、有依据",
        account_name="笛语服饰品牌官方账号",
        operator_name="当前运营者",
        organization_name="笛语服饰",
        content_role_name="品牌官方 / 品牌定义者",
        content_role_boundary="表达品牌判断，不冒充自然人、门店岗位或顾客。",
        audience_description="重视真实感受与关系边界的人。",
        strategy_version="brand-expression-v1",
        platform="小红书",
        media_format="图文",
        production_conditions="原创抽象构成和创作者表达。",
    )


def _request(
    frame: NarrativeFrame | None = None,
    *,
    revision_instruction: str | None = None,
    prior_saved_body: str | None = None,
    products: tuple[ProductFact, ...] = (),
) -> GenerationInput:
    selected_frame = frame or new_frame("general_observation", (), ())
    return GenerationInput(
        run_id=UUID("00000000-0000-0000-0000-000000000101"),
        task_id=UUID("00000000-0000-0000-0000-000000000102"),
        weak_seed="帮我写条婆媳主题的小红书，别狗血，也不要把任何一方写成反派。",
        primary_product="brand_life_narrative",
        revision_instruction=revision_instruction,
        brand=_brand(),
        target="xiaohongshu_graphic",
        media_format="graphic",
        platform_direction=direction_for("xiaohongshu_graphic"),
        active_domain_assets=(
            ActiveAsset(
                "B-001",
                "v1",
                "brand",
                "品牌基线",
                "方法应当尊重关系中的不同位置。",
            ),
        ),
        products=products,
        prior_saved_body=prior_saved_body,
        narrative_frame=selected_frame,
        creative_plan=build_creative_plan(
            topic_spans=("帮我写条婆媳主题的小红书，别狗血，也不要把任何一方写成反派。",),
            primary_value="brand_life_narrative",
            tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
            mechanism_id=None,
            target_shape="xiaohongshu_graphic:graphic",
        ),
    )


def _completion(document: object, tokens: int = 0) -> FakeResponse:
    if isinstance(document, dict):
        if document.get("evidence_version") == REVIEW_EVIDENCE_V2_VERSION:
            return _strict_tool_completion(document, tokens=tokens)
        if document.get("review_version") == CLAUSE_LICENSE_REVIEW_VERSION:
            return _strict_tool_completion(
                document,
                tokens=tokens,
                tool_name=CLAUSE_LICENSE_TOOL_NAME,
            )
    payload: dict[str, Any] = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(document, ensure_ascii=False),
                }
            }
        ]
    }
    if tokens:
        payload["usage"] = {"total_tokens": tokens}
    return FakeResponse(200, payload)


def _strict_tool_completion(
    document: object,
    *,
    tokens: int = 0,
    finish_reason: str = "tool_calls",
    tool_name: str = CLOSED_REVIEW_TOOL_NAME,
) -> FakeResponse:
    payload: dict[str, Any] = {
        "choices": [
            {
                "finish_reason": finish_reason,
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-review-v2",
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(
                                    document,
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    ],
                },
            }
        ]
    }
    if tokens:
        payload["usage"] = {
            "completion_tokens": tokens,
            "total_tokens": tokens,
        }
    return FakeResponse(200, payload)


def _intake_plan(
    message: str,
    *,
    topic_origin: str = "explicit_user",
) -> dict[str, object]:
    return creative_plan_document(
        build_creative_plan(
            topic_spans=(message,),
            primary_value="brand_life_narrative",
            tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
            mechanism_id=None,
            target_shape="xiaohongshu_graphic:graphic",
            topic_origin=cast(Any, topic_origin),
        )
    )


def _sentence_roles(
    message: str,
    fact_ids: tuple[str, ...] = (),
) -> list[dict[str, str]]:
    fact_set = frozenset(fact_ids)
    return [
        {
            "sentence_id": candidate.source_id,
            "role": ("observable_actuality" if candidate.source_id in fact_set else "creation_instruction"),
        }
        for candidate in user_fact_candidates((message,))
    ]


def _mode_text(mode: str, value: str) -> str:
    if mode == "hypothesis":
        return f"如果先停十秒，{value}也许会换一种走向。"
    if mode == "dramatization":
        return f"情境演绎：{value}"
    return value


def _core(frame: NarrativeFrame) -> dict[str, object]:
    values = {
        "title": "关系不是评判赛",
        "natural_guide": "把不同位置放在同一张纸上看，而不是忙着判输赢。",
        "release_caption": "你更愿意给关系留出哪一种空白？",
        "persona_observation": "边界像标点，停顿不等于敌意。",
        "audience_return": "先辨认分歧，再决定是否回应。",
        "brand_account_link": "这个账号愿意把复杂关系讲得不急不躁。",
        "spoken": "两种在意可以同时存在，不必把任何一方写成反派。",
    }
    blocks = [
        {
            "block_id": f"b-{slot}",
            "text": _mode_text(frame.narrative_mode, value),
        }
        for slot, value in values.items()
    ]
    scene_prefix = (
        "情境演绎："
        if frame.narrative_mode == "dramatization"
        else ("如果采用这种表达，" if frame.narrative_mode == "hypothesis" else "")
    )
    scenes: list[dict[str, object]] = [
        {
            "scene_id": "s-cover",
            "resource_refs": ["resource:original_composition"],
            "action_text": scene_prefix + "两组色块保留距离，标题落在中间留白。",
            "sound_text": "",
            "production_note": "使用原创排版和留白。",
        },
        {
            "scene_id": "s-guide",
            "resource_refs": ["resource:original_composition"],
            "action_text": scene_prefix + "抽象标点沿阅读顺序展开。",
            "sound_text": "仅使用不指向现实场景的原创节奏。",
            "production_note": "使用原创图形和文字层级。",
        },
        {
            "scene_id": "s-contract",
            "resource_refs": ["resource:original_composition"],
            "action_text": scene_prefix + "三组标点保持各自位置。",
            "sound_text": "",
            "production_note": "使用原创排版建立阅读层级。",
        },
        {
            "scene_id": "s-spoken",
            "resource_refs": ["resource:original_composition"],
            "action_text": scene_prefix + "抽象线条沿口播节奏展开。",
            "sound_text": "使用原创节奏。",
            "production_note": "不使用现实现场素材。",
        },
        {
            "scene_id": "s-release",
            "resource_refs": ["resource:original_composition"],
            "action_text": scene_prefix + "末段缩小色块并留下开放结尾。",
            "sound_text": "",
            "production_note": "使用原创排版收束阅读节奏。",
        },
    ]
    for index, _ in enumerate(frame.user_facts, start=1):
        scenes.append(
            {
                "scene_id": f"s-actuality-{index}",
                "resource_refs": ["resource:original_composition"],
                "action_text": "原句以纯文字进入阅读顺序，不重演现实现场。",
                "sound_text": "",
                "production_note": "只用原创排版承载用户原句。",
            }
        )
    return {"blocks": blocks, "scenes": scenes}


def _targets(
    core: dict[str, object],
    frame: NarrativeFrame,
) -> list[tuple[str, str, str]]:
    blocks = core["blocks"]
    scenes = core["scenes"]
    assert isinstance(blocks, list)
    assert isinstance(scenes, list)
    targets = [(str(block["block_id"]), "block", str(block["text"])) for block in blocks if isinstance(block, dict)]
    targets.extend(
        (
            f"actuality:{index}",
            "block",
            fact.exact_text,
        )
        for index, fact in enumerate(frame.user_facts, start=1)
    )
    for scene in scenes:
        assert isinstance(scene, dict)
        text = "\n".join(str(scene[key]) for key in ("action_text", "sound_text", "production_note") if scene.get(key))
        targets.append((str(scene["scene_id"]), "scene", text))
    return targets


def _observations(
    core: dict[str, object],
    frame: NarrativeFrame,
    *,
    changes: dict[str, dict[str, object]] | None = None,
    omitted: frozenset[str] = frozenset(),
) -> dict[str, object]:
    changes = changes or {}
    observations: list[dict[str, object]] = []
    for target_id, target_kind, text in _targets(core, frame):
        if target_id in omitted:
            continue
        if target_id.startswith("actuality:"):
            binding = "user_actuality"
        elif target_kind == "scene" or frame.narrative_mode == "actuality_reflection":
            binding = "dramatization" if frame.narrative_mode == "dramatization" else "abstract_principle"
        else:
            binding = "abstract_principle" if frame.narrative_mode == "general_observation" else frame.narrative_mode
        observation: dict[str, object] = {
            "id": target_id,
            "target_kind": target_kind,
            "text_spans": [text],
            "people": [],
            "relationships": [],
            "actions_or_events": [],
            "dialogue": [],
            "motives": [],
            "causes": [],
            "results": [],
            "times": [],
            "locations": [],
            "possessions": [],
            "observation_type": binding,
            "resource_refs": (["resource:original_composition"] if target_kind == "scene" else []),
            "dramatization_disclosure_spans": (["情境演绎"] if binding == "dramatization" else []),
            "instruction_conflicts": [],
            "uncertain": False,
        }
        observation.update(changes.get(target_id, {}))
        claims: list[dict[str, str]] = []
        for category in (
            "people",
            "relationships",
            "actions_or_events",
            "dialogue",
            "motives",
            "causes",
            "results",
            "times",
            "locations",
            "possessions",
        ):
            values = observation.pop(category)
            assert isinstance(values, list)
            claims.extend({"category": category, "span": str(value)} for value in values)
        observation["claims"] = claims
        observations.append(observation)
    return {"observations": observations}


def _payload_prompts() -> list[str]:
    prompts: list[str] = []
    for request in FakeClient.requests:
        payload = request["json"]
        assert isinstance(payload, dict)
        messages = payload["messages"]
        assert isinstance(messages, list)
        user_message = messages[1]
        assert isinstance(user_message, dict)
        prompts.append(str(user_message["content"]))
    return prompts


def _kernel_request(
    frame: NarrativeFrame | None = None,
    *,
    revision_instruction: str | None = None,
    prior_kernel: CreativeKernelV1 | None = None,
) -> GenerationInput:
    return replace(
        _request(
            frame,
            revision_instruction=revision_instruction,
        ),
        delivery_compiler_version=DUAL_TRACK_DELIVERY_COMPILER_VERSION,
        prior_creative_kernel=prior_kernel,
    )


def _kernel_writer(
    *,
    body: str = "换位思考不等于没有边界。",
    title: str = "边界不是一道判决题",
    observation_only: bool = False,
) -> dict[str, object]:
    body_units = (
        [{"unit_id": "unit:body", "text": body}]
        if observation_only
        else [
            {"unit_id": "unit:body-opening", "text": body},
            {
                "unit_id": "unit:hypothetical-example",
                "text": "一方先停一下，另一方也不必马上给出答案。",
            },
            {
                "unit_id": "unit:body-closing",
                "text": "理解可以靠近，边界也仍然成立。",
            },
        ]
    )
    return {
        "units": [
            {"unit_id": "unit:title", "text": title},
            *body_units,
        ]
    }


def _parsed_kernel(
    request: GenerationInput,
    raw: dict[str, object],
) -> CreativeKernelV1:
    assert request.narrative_frame is not None
    context = BoundaryContext.from_request(
        request,
        request.narrative_frame,
    )
    skeleton = build_kernel_skeleton(
        frame=request.narrative_frame,
        fact_registry=context.fact_registry,
        constraint_refs=tuple(identifier for identifier, _ in context.constraint_registry),
        program_id=select_kernel_program(
            frame=request.narrative_frame,
            prior_kernel=request.prior_creative_kernel,
        ),
    )
    return parse_writer_kernel(
        raw,
        skeleton,
        compiler_owned_text_by_id=compiler_owned_unit_texts(request.primary_product),
    )


def test_kernel_writer_prompt_exposes_current_trusted_contracts() -> None:
    request = _kernel_request()
    prompt = _generator()._kernel_writer_prompt(
        request,
        _parsed_kernel(request, _kernel_writer()),
    )

    assert "recommendation 必须写清楚这是可以怎样做的建议" in prompt
    assert '"unit_id": "unit:body-closing"' in prompt
    assert '"track": "creative_expression"' in prompt
    assert '"mode": "general_observation"' in prompt
    assert "Writer-owned clause 不得让当前表达者或第一人称复数承担" in prompt
    assert "abstract_observation\n只写状态、判断、关系理解或比喻" in prompt
    assert "actuality_reflection 对应的用户现实原文" in prompt
    assert "Writer 只能写不复述该事实的抽象关系反思" in prompt
    assert "不能复制、概括或扩写人物、动作、对白、动机、原因、结果" in prompt


def test_kernel_reviewer_prompt_binds_recombined_frozen_event_details() -> None:
    frame = new_frame(
        "actuality_reflection",
        ("今天店里忙了一天，回家还因为谁洗碗拌了两句。",),
        (),
    )
    request = _kernel_request(frame)
    context = BoundaryContext.from_request(request, frame)
    kernel = _parsed_kernel(
        request,
        _kernel_writer(observation_only=True),
    )
    contexts = build_clause_contexts_v2(
        kernel=kernel,
        frame=frame,
        fact_registry=context.fact_registry,
        allowed_constraint_ids=context.constraint_ids,
        speaker_kind=request.brand.speaker_kind,
    )
    writer_contexts = tuple(item for item in contexts if item.text_source == "writer_unit")
    questions = build_closed_review_questions(writer_contexts)

    prompt = _generator()._kernel_reviewer_prompt(
        questions=questions,
        contexts=writer_contexts,
        actuality_facts=tuple(
            (item.fact_id, item.exact_text) for item in context.fact_registry if item.fact_kind == "user_actuality"
        ),
        protected_subjects=(),
    )

    assert "把同一条冻结事实中的多个具体细节重新组合成" in prompt
    assert "即使没有第一人称，也属于 current_user" in prompt
    assert "重新组合其具体细节" in prompt


def test_kernel_writer_prompt_hides_product_facts_and_fact_authorship() -> None:
    product = ProductFact(
        sku="ZX-C218",
        display_name="双面短外套",
        facts={
            "entity_kind": "apparel_product",
            "material": "棉混纺",
            "sample_weight_m_grams": 620,
        },
    )
    fact_ids = tuple(record.fact_id for record in product_fact_records(product))
    frame = new_frame("general_observation", (), fact_ids)
    request = replace(
        _kernel_request(frame),
        products=(product,),
    )
    context = BoundaryContext.from_request(request, frame)
    skeleton = build_kernel_skeleton(
        frame=frame,
        fact_registry=context.fact_registry,
        constraint_refs=tuple(context.constraint_ids),
        program_id=select_kernel_program(
            frame=frame,
            prior_kernel=None,
        ),
    )
    packet = build_product_fact_packet(
        (product,),
        allowed_fact_ids=frame.allowed_product_fact_ids,
    )
    skeleton = replace(
        skeleton,
        selected_fact_block_ids=select_product_fact_block_ids(
            packet,
            limit=3,
        ),
    )

    prompt = _generator()._kernel_writer_prompt(request, skeleton)

    assert "双面短外套" not in prompt
    assert "棉混纺" not in prompt
    assert "620" not in prompt
    assert "ZX-C218" not in prompt
    assert "selected_fact_block_count" in prompt
    assert "不授权 Writer 选择或引用事实" in prompt
    assert "可信事实块和登记资源已由服务端冻结" in prompt
    assert "deidentified-product-writer-brief-v1" in prompt
    assert "根对象必须恰好只有 units" in prompt
    assert '"claim_refs"' not in prompt
    assert "禁止返回 fact_block_refs、claim_refs" in prompt
    assert any(unit.purpose == "frozen_fact" and unit.text == "双面短外套的材质是棉混纺。" for unit in skeleton.units)


def test_kernel_repair_prompt_explains_stable_issue_responsibilities() -> None:
    request = _kernel_request()
    kernel = _parsed_kernel(request, _kernel_writer())
    affected = frozenset({"unit:body-opening"})
    prompt = _generator()._kernel_repair_prompt(
        request,
        kernel,
        affected,
        (
            NarrativeIssue(
                "unit:body-opening",
                "situated_event_in_observation",
                "问题片段",
            ),
            NarrativeIssue(
                "unit:body-opening",
                "unsupported_actuality_expansion",
                "另一问题片段",
            ),
        ),
    )

    assert "把完整 unit 重写为其冻结" in prompt
    assert "只对服务端已经逐字插入的\n  事实作抽象反思" in prompt
    assert "现实原文\n  已由服务端 frozen fact 单元独立保留" in prompt
    assert "每个返回 unit 的文字都必须与 current_text 实质不同" in prompt
    assert "不得原样返回、只换标点或把问题句移动到另一个 unit" in prompt
    assert "这是本成品唯一修复" in prompt
    assert "只写一至两句纯状态、关系或价值判断" in prompt
    assert "用户事实中没有逐字出现的亲属、伴侣、同住、员工、顾客" in prompt


def test_kernel_repair_prompt_never_exposes_service_disclosure_as_writer_text() -> None:
    request = _kernel_request()
    kernel = _parsed_kernel(request, _kernel_writer())

    prompt = _generator()._kernel_repair_prompt(
        request,
        kernel,
        frozenset({"unit:hypothetical-example"}),
        (
            NarrativeIssue(
                "unit:hypothetical-example",
                "unsupported_actuality_binding",
                "问题片段",
            ),
        ),
    )

    assert '"current_text": "一方先停一下，另一方也不必马上给出答案。"' in prompt
    assert '"current_text": "假设有这样一幕：' not in prompt
    assert "修复文字不得重复\n这些包裹" in prompt


def test_actuality_revision_repair_replays_reviewed_unit_not_failed_draft() -> None:
    frame = new_frame(
        "actuality_reflection",
        ("今天店里忙了一天，回家还因为谁洗碗拌了两句。",),
        (),
    )
    first_request = _kernel_request(frame)
    prior = _parsed_kernel(
        first_request,
        _kernel_writer(
            body="疲惫会放大小事，理解不必变成一场输赢。",
            observation_only=True,
        ),
    )
    revision = _kernel_request(
        frame,
        revision_instruction="别讲道理，荒诞一点。",
        prior_kernel=prior,
    )
    failed = replace(
        prior,
        units=tuple(
            replace(
                unit,
                text="疲惫的碰撞在厨房里发酵，洗碗池成了无声的战场。",
            )
            if unit.unit_id == "unit:body"
            else unit
            for unit in prior.units
        ),
    )

    prompt = _generator()._kernel_repair_prompt(
        revision,
        failed,
        frozenset({"unit:body"}),
        (
            NarrativeIssue(
                "unit:body",
                "statement_mode_conflict",
                "疲惫的碰撞在厨房里发酵，洗碗池成了无声的战场。",
            ),
        ),
    )

    assert "prior_reviewed_text" in prompt
    assert "疲惫会放大小事，理解不必变成一场输赢。" in prompt
    assert "疲惫的碰撞在厨房里发酵" not in prompt
    assert "洗碗池" not in prompt
    assert "今天店里忙了一天" not in prompt
    assert "本次表达要求：别讲道理，荒诞一点。" in prompt
    assert "一般建议必须使用\n  明确的条件或可选语态" in prompt
    assert "健康、身体改善、心理、需要、意图、原因、因果或结果" in prompt
    assert "不得复述\n  真人事实、安排已发生事件" in prompt


def test_first_actuality_repair_does_not_replay_fact_or_failed_draft() -> None:
    frame = new_frame(
        "actuality_reflection",
        ("今天店里忙了一天，回家还因为谁洗碗拌了两句。",),
        (),
    )
    request = _kernel_request(frame)
    failed_text = "洗碗这件小事，藏着多少夫妻的默契。"
    failed = _parsed_kernel(
        request,
        _kernel_writer(
            title=failed_text,
            observation_only=True,
        ),
    )

    prompt = _generator()._kernel_repair_prompt(
        request,
        failed,
        frozenset({"unit:title"}),
        (
            NarrativeIssue(
                "unit:title",
                "unsupported_actuality_expansion",
                failed_text,
            ),
        ),
    )

    assert failed_text not in prompt
    assert "今天店里忙了一天" in prompt
    assert "只用于理解主题" in prompt
    assert "禁止在返回\n文字中复制、概括、换词复述或扩展" in prompt
    assert '"prior_reviewed_text":' not in prompt
    assert '"unit_id": "unit:title"' in prompt
    assert "不得绑定当前\n  用户、机构、现实事件或任何具体关系身份" in prompt
    assert "body 用三至五个短 clause" in prompt
    assert "不能只写\n一句安全口号" in prompt


def test_product_fact_repair_does_not_replay_offending_fact_text() -> None:
    product = ProductFact(
        sku="ZX-C218",
        display_name="双面短外套",
        facts={
            "entity_kind": "apparel_product",
            "category": "短外套",
            "material": "棉混纺",
        },
    )
    records = product_fact_records(product)
    frame = new_frame(
        "general_observation",
        (),
        tuple(record.fact_id for record in records),
    )
    request = replace(
        _kernel_request(frame),
        products=(product,),
    )
    context = BoundaryContext.from_request(request, frame)
    skeleton = build_kernel_skeleton(
        frame=frame,
        fact_registry=context.fact_registry,
        constraint_refs=tuple(context.constraint_ids),
        program_id=select_kernel_program(
            frame=frame,
            prior_kernel=None,
        ),
    )
    selected = tuple(block.fact_block_id for block in context.product_fact_blocks[:2])
    violating_text = "双面短外套的材质是棉混纺。"
    kernel = parse_writer_kernel(
        {
            "fact_block_refs": list(selected),
            "units": [
                {
                    "unit_id": unit.unit_id,
                    "text": (violating_text if unit.unit_id == "unit:body" else "先看清楚，再保留选择。"),
                    "claim_refs": [context.product_fact_blocks[0].fact_id],
                }
                for unit in skeleton.writable_units
            ],
        },
        skeleton,
        fact_blocks=context.product_fact_blocks,
        allowed_claim_ids=context.product_fact_packet.fact_ids,
    )

    prompt = _generator()._kernel_repair_prompt(
        request,
        kernel,
        frozenset({"unit:body"}),
        (
            NarrativeIssue(
                "unit:body",
                "product_fact_must_use_immutable_block",
                violating_text,
            ),
        ),
    )

    assert "ZX-C218" not in prompt
    assert "双面短外套" not in prompt
    assert "棉混纺" not in prompt
    assert '"apparel_product"' not in prompt
    assert violating_text not in prompt
    assert '"current_text"' not in prompt
    assert '"claim_refs": []' in prompt
    assert "你看不到、也不需要复述、解释或推断这些事实" in prompt
    assert "围绕服务端已经冻结的本件商品价值关系" in prompt
    assert "不能退回适用于任意商品的阅读步骤" in prompt
    assert "claim_refs 必须\n是空数组" in prompt
    assert '"unit_contract": "audience_guidance"' in prompt
    assert "只写一至两句与已插入事实配套的观看回报" in prompt
    assert "不得因为 purpose 或写作习惯换成建议、假设、演绎" in prompt
    assert "只谈读者如何看、如何选、如何保留判断" in prompt
    assert "不得输出“抽象原则”等内部合同语言" in prompt
    assert "不得成为创意文字的主语、宾语或指代对象" in prompt
    assert "文字不能出现商品名称、编号或改写硬属性" in prompt
    assert "去掉这条价值命题后不应仍可无损套用到任意商品" in prompt
    assert "使用自然第二人称直接和受众说话" in prompt
    assert "body 用二至四个短 clause" in prompt
    assert "release_caption 留下一个可以直接回答" in prompt
    assert "xiaohongshu_graphic / graphic" in prompt
    assert request.brand.content_role_boundary in prompt
    assert request.brand.positioning not in prompt
    assert request.brand.decision_order not in prompt
    assert request.brand.tone not in prompt


def test_product_fact_ownership_repair_rewrites_one_coherent_creative_set() -> None:
    product = ProductFact(
        sku="ZX-C218",
        display_name="双面短外套",
        facts={
            "entity_kind": "apparel_product",
            "colors": ["炭灰纯色", "深绿细格纹"],
        },
    )
    fact_ids = tuple(record.fact_id for record in product_fact_records(product))
    frame = new_frame("general_observation", (), fact_ids)
    request = replace(
        _kernel_request(frame),
        products=(product,),
    )
    context = BoundaryContext.from_request(request, frame)
    skeleton = build_kernel_skeleton(
        frame=frame,
        fact_registry=context.fact_registry,
        constraint_refs=tuple(context.constraint_ids),
        program_id=select_kernel_program(
            frame=frame,
            prior_kernel=None,
        ),
    )
    selected = tuple(block.fact_block_id for block in context.product_fact_blocks[:2])
    kernel = parse_writer_kernel(
        {
            "fact_block_refs": list(selected),
            "units": [
                {
                    "unit_id": unit.unit_id,
                    "text": "先看清楚，再保留选择。",
                    "claim_refs": [],
                }
                for unit in skeleton.writable_units
            ],
        },
        skeleton,
        fact_blocks=context.product_fact_blocks,
        allowed_claim_ids=context.product_fact_packet.fact_ids,
    )

    affected = _generator()._kernel_repair_scope(
        kernel,
        (
            NarrativeIssue(
                "unit:body",
                "unsupported_product_inference",
                "越界片段",
            ),
        ),
    )

    assert affected == frozenset(unit.unit_id for unit in kernel.writable_units)


def _kernel_observations(
    kernel: CreativeKernelV1,
    *,
    request: GenerationInput | None = None,
    body_type: str | None = None,
    omit: frozenset[str] = frozenset(),
    partial: frozenset[str] = frozenset(),
) -> dict[str, object]:
    active_request = request or _kernel_request()
    assert active_request.narrative_frame is not None
    context = BoundaryContext.from_request(
        active_request,
        active_request.narrative_frame,
    )
    clause_contexts = build_clause_contexts_v2(
        kernel=kernel,
        frame=active_request.narrative_frame,
        fact_registry=context.fact_registry,
        allowed_constraint_ids=context.constraint_ids,
        speaker_kind=active_request.brand.speaker_kind,
    )
    questions = build_closed_review_questions(clause_contexts)
    contexts_by_clause = {clause_context.clause_id: clause_context for clause_context in clause_contexts}
    answers: list[dict[str, object]] = []
    for question in questions:
        clause_context = contexts_by_clause[question.clause_id]
        if clause_context.unit_id in omit:
            continue
        is_event = (
            clause_context.unit_id == "unit:body-opening"
            and body_type == "situated_event"
            and question.dimension == "actual_event"
        )
        uncertain: object = False
        if question.dimension == "statement_mode":
            mode_by_contract = {
                "abstract_observation": "generic_observation",
                "audience_guidance": "generic_observation",
                "recommendation": "recommendation",
                "hypothetical_example": "hypothesis",
                "disclosed_dramatization": "dramatization",
                "actuality_reflection": "generic_observation",
            }
            operands = [mode_by_contract[clause_context.unit_contract]]
        elif is_event:
            operands = ["event"]
        else:
            operands = []
        if clause_context.unit_id in partial and question.dimension == "statement_mode":
            uncertain = "false"
        answers.append(
            {
                "question_id": question.question_id,
                "uncertain": uncertain,
                "operands": operands,
            }
        )
    return {
        "evidence_version": CLOSED_REVIEW_VERSION,
        "answers": answers,
    }


def _kernel_license_reviews(
    kernel: CreativeKernelV1,
    *,
    request: GenerationInput | None = None,
    body_type: str | None = None,
    omit: frozenset[str] = frozenset(),
) -> dict[str, object]:
    active_request = request or _kernel_request()
    assert active_request.narrative_frame is not None
    frame = active_request.narrative_frame
    context = BoundaryContext.from_request(active_request, frame)
    clause_contexts = build_clause_contexts_v2(
        kernel=kernel,
        frame=frame,
        fact_registry=context.fact_registry,
        allowed_constraint_ids=context.constraint_ids,
        speaker_kind=active_request.brand.speaker_kind,
    )
    policies = build_unit_clause_license_policies_v1(
        frame=frame,
        unit_contracts=unit_contracts_v2(kernel, frame),
    )
    licenses = materialize_clause_licenses_v1(
        contexts=clause_contexts,
        policies=policies,
    )
    context_by_clause = {item.clause_id: item for item in clause_contexts}
    reviews: list[dict[str, object]] = []
    for license_ in licenses:
        context_item = context_by_clause[license_.clause_id]
        if context_item.unit_id in omit:
            continue
        is_event = context_item.unit_id == "unit:body-opening" and body_type == "situated_event"
        quote_candidates = unsupported_quote_candidates_v1(context_item.exact_text)
        reviews.append(
            {
                "clause_id": license_.clause_id,
                "license_id": license_.license_id,
                "verdict": ("unsupported" if is_event else "supported"),
                "expression_type": (
                    "generic_observation"
                    if "generic_observation" in license_.allowed_expression_types
                    else license_.allowed_expression_types[0]
                ),
                "binding_checks": [
                    {
                        "binding_id": binding,
                        "status": ("present" if is_event and binding == "actual_event_or_result" else "absent"),
                    }
                    for binding in license_.prohibited_bindings
                ],
                "reason_code": ("actual_event_or_result" if is_event else "supported_by_license"),
                "unsupported_quote": (quote_candidates[0] if is_event else ""),
            }
        )
    return {
        "review_version": CLAUSE_LICENSE_REVIEW_VERSION,
        "reviews": reviews,
    }


def test_conversation_intake_preserves_exact_spans_and_mode() -> None:
    message = "今天店里忙了一天，回家还因为谁洗碗拌了两句。帮我发条小红书。"
    request = ConversationInput(
        message=message,
        history=(),
        brand=_brand(),
        products=(),
        target="xiaohongshu_graphic",
        allowed_tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
        platform_shape="xiaohongshu_graphic:graphic",
    )
    prompt = _generator()._conversation_prompt(request)
    candidates = user_fact_candidates((message,))
    fact_candidate = next(
        candidate for candidate in candidates if candidate.exact_text == "今天店里忙了一天，回家还因为谁洗碗拌了两句。"
    )
    instruction_candidates = tuple(
        candidate.source_id for candidate in candidates if candidate.source_id != fact_candidate.source_id
    )
    assert "narrative_mode 由\n  服务端根据显式形式与完整事实句选择派生" in prompt
    assert "你不得返回或选择该字段" in prompt
    assert "primary_value 是本篇给受众的主要回报，不是 narrative_mode" in prompt
    assert "没有选题但要求生成”\n  通常选 brand_life_narrative" in prompt
    FakeClient.responses = [
        _completion(
            {
                "kind": "ready",
                "message": "好，我保留这段原话，其他由我来完成。",
                "user_premises": [message],
                "user_fact_sentence_ids": [fact_candidate.source_id],
                "user_instruction_sentence_ids": list(instruction_candidates),
                "user_sentence_roles": _sentence_roles(
                    message,
                    (fact_candidate.source_id,),
                ),
                "narrative_mode": "general_observation",
                "creative_plan": _intake_plan(message),
            }
        )
    ]
    decision = _generator().collaborate(request)
    assert decision.disposition == "ready"
    assert decision.user_premises == (message,)
    assert decision.user_fact_spans == ("今天店里忙了一天，回家还因为谁洗碗拌了两句。",)
    assert decision.user_fact_source_ids == (fact_candidate.source_id,)
    assert decision.narrative_mode == "actuality_reflection"


def test_single_turn_intake_keeps_the_server_owned_premise_when_the_model_paraphrases() -> None:
    message = "店里有个人只想自己看看，不想被打扰。请给一条尚未执行的回应建议。"
    candidates = user_fact_candidates((message,))
    fact_candidate = next(
        candidate for candidate in candidates if candidate.exact_text == "店里有个人只想自己看看，不想被打扰。"
    )
    request = ConversationInput(
        message=message,
        history=(),
        brand=_brand(),
        products=(),
        target="xiaohongshu_graphic",
        creation_committed=True,
        allowed_tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
        platform_shape="xiaohongshu_graphic:graphic",
    )
    FakeClient.responses = [
        _completion(
            {
                "kind": "ready",
                "message": "好，我保留事实边界并直接完成。",
                "user_premises": ["有人只想安静看看，请给一条回应建议。"],
                "user_fact_sentence_ids": [fact_candidate.source_id],
                "user_sentence_roles": _sentence_roles(
                    message,
                    (fact_candidate.source_id,),
                ),
                "creative_plan": _intake_plan(message),
            }
        )
    ]

    decision = _generator().collaborate(request)

    assert decision.user_premises == (message,)
    assert decision.user_fact_spans == (fact_candidate.exact_text,)


def test_conversation_intake_freezes_system_selected_topic_origin() -> None:
    message = "今天不知道发什么，帮我做条小红书。"
    candidates = user_fact_candidates((message,))
    request = ConversationInput(
        message=message,
        history=(),
        brand=_brand(),
        products=(),
        target="xiaohongshu_graphic",
        creation_committed=True,
        allowed_tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
        platform_shape="xiaohongshu_graphic:graphic",
        user_fact_candidates=candidates,
    )
    FakeClient.responses = [
        _completion(
            {
                "kind": "ready",
                "message": "好，我会从当前账号内容领地选择一个具体主线。",
                "user_premises": [message],
                "user_fact_sentence_ids": [],
                "user_sentence_roles": _sentence_roles(message),
                "creative_plan": _intake_plan(
                    message,
                    topic_origin="system_selected",
                ),
                "creation_proposal": True,
            }
        )
    ]

    decision = _generator().collaborate(request)

    assert decision.creative_plan is not None
    assert decision.creative_plan.plan_version == PLAN_VERSION
    assert decision.creative_plan.topic_origin == "system_selected"


def test_conversation_intake_keeps_frozen_actuality_as_the_explicit_topic() -> None:
    message = "今天事情一件接一件，回到家才发现自己连水都忘了喝，帮我发一条。"
    candidates = user_fact_candidates((message,))
    actuality = candidates[0]
    request = ConversationInput(
        message=message,
        history=(),
        brand=_brand(),
        products=(),
        target="xiaohongshu_graphic",
        creation_committed=True,
        allowed_tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
        platform_shape="xiaohongshu_graphic:graphic",
        user_fact_candidates=candidates,
    )
    FakeClient.responses = [
        _completion(
            {
                "kind": "ready",
                "message": "好，我会回应这段具体生活片段。",
                "user_premises": [message],
                "user_fact_sentence_ids": [actuality.source_id],
                "user_sentence_roles": _sentence_roles(
                    message,
                    (actuality.source_id,),
                ),
                # This is the exact bad model projection seen in the WIP
                # suite.  The server must not let it grant account-domain
                # topic selection once actuality has been frozen.
                "creative_plan": _intake_plan(
                    message,
                    topic_origin="system_selected",
                ),
                "creation_proposal": True,
            }
        )
    ]

    decision = _generator().collaborate(request)

    assert decision.user_fact_spans == (message,)
    assert decision.narrative_mode == "actuality_reflection"
    assert decision.creative_plan is not None
    assert decision.creative_plan.topic_origin == "explicit_user"


def test_conversation_intake_freezes_the_whole_negated_sentence() -> None:
    message = "我没有和婆婆吵架。帮我写条小红书。"
    candidates = user_fact_candidates((message,))
    negated = next(candidate for candidate in candidates if candidate.exact_text == "我没有和婆婆吵架。")
    instruction_candidates = tuple(
        candidate.source_id for candidate in candidates if candidate.source_id != negated.source_id
    )
    request = ConversationInput(
        message=message,
        history=(),
        brand=_brand(),
        products=(),
        target="xiaohongshu_graphic",
        allowed_tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
        platform_shape="xiaohongshu_graphic:graphic",
        user_fact_candidates=candidates,
    )
    FakeClient.responses = [
        _completion(
            {
                "kind": "ready",
                "message": "好，我会保留完整原话。",
                "user_premises": [message],
                "user_fact_sentence_ids": [negated.source_id],
                "user_instruction_sentence_ids": list(instruction_candidates),
                "user_sentence_roles": _sentence_roles(
                    message,
                    (negated.source_id,),
                ),
                "creative_plan": _intake_plan(message),
            }
        )
    ]

    decision = _generator().collaborate(request)

    assert decision.user_fact_spans == ("我没有和婆婆吵架。",)
    assert decision.user_fact_source_ids == (negated.source_id,)


def test_conversation_intake_rejects_model_selected_fact_substrings() -> None:
    message = "我没有和婆婆吵架。帮我写条小红书。"
    FakeClient.responses = [
        _completion(
            {
                "kind": "ready",
                "message": "开始。",
                "user_premises": [message],
                "user_fact_spans": ["和婆婆吵架"],
                "creative_plan": _intake_plan(message),
            }
        )
    ]

    with pytest.raises(GenerationFailed, match="格式不完整"):
        _generator().collaborate(
            ConversationInput(
                message=message,
                history=(),
                brand=_brand(),
                products=(),
                target="xiaohongshu_graphic",
                allowed_tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
                platform_shape="xiaohongshu_graphic:graphic",
            )
        )


def test_conversation_intake_keeps_creation_instruction_out_of_frozen_actuality() -> None:
    message = "今天店里有人只想自己看看。请回应这种状态，不补写顾客身份、对白或结果。"
    candidates = user_fact_candidates((message,))
    fact = next(candidate for candidate in candidates if candidate.exact_text == "今天店里有人只想自己看看。")
    instruction = next(candidate for candidate in candidates if candidate.source_id != fact.source_id)
    request = ConversationInput(
        message=message,
        history=(),
        brand=_brand(),
        products=(),
        target="xiaohongshu_graphic",
        allowed_tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
        platform_shape="xiaohongshu_graphic:graphic",
        user_fact_candidates=candidates,
    )
    FakeClient.responses = [
        _completion(
            {
                "kind": "ready",
                "message": "好，我只保留实际观察。",
                "user_premises": [message],
                "user_fact_sentence_ids": [fact.source_id],
                "user_instruction_sentence_ids": [instruction.source_id],
                "user_sentence_roles": _sentence_roles(
                    message,
                    (fact.source_id,),
                ),
                "creative_plan": _intake_plan(message),
            }
        )
    ]

    decision = _generator().collaborate(request)

    assert decision.user_fact_spans == (fact.exact_text,)
    assert decision.user_fact_source_ids == (fact.source_id,)
    assert decision.user_instruction_source_ids == (instruction.source_id,)


@pytest.mark.parametrize(
    ("message", "mode", "facts"),
    (
        (
            "帮我写条婆媳主题的小红书。",
            "general_observation",
            [],
        ),
        (
            "如果两个人都先停十秒再回应，把这个想法写成小红书。",
            "hypothesis",
            [],
        ),
        (
            "把婆媳关系写成一段明确的情境演绎，不绑定真实人物。",
            "dramatization",
            [],
        ),
    ),
)
def test_conversation_intake_accepts_the_three_nonactual_modes(
    message: str,
    mode: NarrativeMode,
    facts: list[str],
) -> None:
    FakeClient.responses = [
        _completion(
            {
                "kind": "ready",
                "message": "可以，直接开始。",
                "user_premises": [message],
                "user_fact_sentence_ids": facts,
                "user_instruction_sentence_ids": [
                    candidate.source_id for candidate in user_fact_candidates((message,))
                ],
                "user_sentence_roles": _sentence_roles(message),
                "narrative_mode": mode,
                "creative_plan": _intake_plan(message),
            }
        )
    ]
    decision = _generator().collaborate(
        ConversationInput(
            message,
            (),
            _brand(),
            (),
            "xiaohongshu_graphic",
            explicit_narrative_mode=(mode if mode in {"hypothesis", "dramatization"} else None),
            allowed_tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
            platform_shape="xiaohongshu_graphic:graphic",
        )
    )
    assert decision.narrative_mode == mode
    assert decision.user_fact_spans == ()


def test_conversation_question_must_bind_one_user_fact_gap() -> None:
    message = "把我去年创业最困难的那个月写出来。"
    FakeClient.responses = [
        _completion(
            {
                "kind": "question",
                "message": "那个月具体发生了哪一件最让你觉得困难的事？",
                "missing_fact_span": "去年创业最困难的那个月",
            }
        )
    ]
    decision = _generator().collaborate(
        ConversationInput(
            message,
            (ConversationTurn("assistant", "你可以只说最关键的一件事。"),),
            _brand(),
            (),
            "xiaohongshu_graphic",
            indispensable_fact_question_allowed=True,
        )
    )
    assert decision.disposition == "question"
    assert "具体发生" in decision.message


def test_committed_low_seed_cannot_be_returned_as_an_unnecessary_question() -> None:
    message = "今天喝了一直喝的蓝山咖啡，居然是甜的"
    request = ConversationInput(
        message=message,
        history=(),
        brand=_brand(),
        products=(),
        target="xiaohongshu_graphic",
        creation_committed=True,
        indispensable_fact_question_allowed=False,
        allowed_tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
        platform_shape="xiaohongshu_graphic:graphic",
    )
    prompt = _generator()._conversation_prompt(request)
    assert "服务端允许不可替代事实追问=\n  false" in prompt
    FakeClient.responses = [
        _completion(
            {
                "kind": "question",
                "message": "还需要补充一点细节。",
                "missing_fact_span": message,
                "creation_proposal": True,
            }
        )
    ]

    with pytest.raises(GenerationFailed, match="不允许.*退回追问"):
        _generator().collaborate(request)


def test_series_intake_does_not_turn_continuation_instruction_into_actuality() -> None:
    request = ConversationInput(
        message="继续下一篇：怎样在对方明确回应时接住话题。",
        history=(),
        brand=_brand(),
        products=(),
        target="xiaohongshu_graphic",
        prior_series_summary="系列第 2 个位置；已有 1 条必要前情。",
        creation_committed=True,
        allowed_tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
        platform_shape="xiaohongshu_graphic:graphic",
    )

    prompt = _generator()._conversation_prompt(request)

    assert "当前存在冻结系列前情" in prompt
    assert "都是 creation_instruction，不是已经发生的现实" in prompt
    assert "只有单独" in prompt
    assert "陈述且具有可观察动作、事件、对白或结果" in prompt


def test_conversation_rejects_synthetic_or_mode_drifted_spans() -> None:
    message = "帮我写条婆媳主题的小红书。"
    FakeClient.responses = [
        _completion(
            {
                "kind": "ready",
                "message": "开始。",
                "user_premises": [message],
                "user_fact_sentence_ids": ["source:user_actuality:invented"],
                "user_instruction_sentence_ids": [
                    candidate.source_id for candidate in user_fact_candidates((message,))
                ],
                "user_sentence_roles": _sentence_roles(message),
                "narrative_mode": "actuality_reflection",
                "creative_plan": _intake_plan(message),
            }
        )
    ]
    with pytest.raises(GenerationFailed, match="事实句标识不存在"):
        _generator().collaborate(
            ConversationInput(
                message,
                (),
                _brand(),
                (),
                "xiaohongshu_graphic",
                allowed_tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
                platform_shape="xiaohongshu_graphic:graphic",
            )
        )


def test_writer_cannot_author_or_modify_service_actuality() -> None:
    frame = new_frame(
        "actuality_reflection",
        ("今天店里忙了一天，回家还因为谁洗碗拌了两句。",),
        (),
    )
    request = _request(frame)
    core = _core(frame)
    blocks = core["blocks"]
    assert isinstance(blocks, list)
    blocks.append(
        {
            "block_id": "writer-actuality",
            "block_type": "actuality_source",
            "slot": "spoken",
            "text": "丈夫最后去洗了碗。",
            "source_refs": ["source:user_actuality:1"],
            "linked_scene_ids": ["s-body"],
        }
    )
    FakeClient.responses = [_completion(core)]
    with pytest.raises(GenerationFailed, match="类型化成品不完整"):
        _generator()._generate_legacy(request)


@pytest.mark.parametrize(
    "mode",
    (
        "general_observation",
        "actuality_reflection",
        "hypothesis",
        "dramatization",
    ),
)
def test_full_candidate_is_independently_reviewed_and_digest_locked(
    mode: str,
) -> None:
    frame = new_frame(
        mode,  # type: ignore[arg-type]
        (("今天店里忙了一天，回家还因为谁洗碗拌了两句。",) if mode == "actuality_reflection" else ()),
        (),
    )
    request = _request(frame)
    core = _core(frame)
    FakeClient.responses = [
        _completion(core, 100),
        _completion(_observations(core, frame), 50),
    ]
    artifact = _generator()._generate_legacy(request)
    assert isinstance(artifact.production, GraphicProductionBundle)
    assert artifact.reviewed_digest == visible_digest(artifact.outline, artifact.body)
    for fact in frame.user_facts:
        assert fact.exact_text in artifact.body
    assert artifact.provider_usage is not None
    assert artifact.provider_usage["total_tokens"] == 150
    assert artifact.provider_usage["writer_model"] == "deepseek-test"
    assert artifact.provider_usage["reviewer_model"] == "deepseek-test"
    prompts = _payload_prompts()
    assert len(prompts) == 2
    assert "最终完整可见成品" in prompts[1]
    assert '"block_type"' not in prompts[1]
    assert '"source_refs"' not in prompts[1]
    assert core["blocks"] != prompts[1]


def test_reviewer_must_cover_every_target_with_an_existing_span() -> None:
    frame = new_frame("general_observation", (), ())
    core = _core(frame)
    bad = _observations(
        core,
        frame,
        changes={"b-spoken": {"text_spans": ["并不存在的句子"]}},
        omitted=frozenset({"s-cover"}),
    )
    FakeClient.responses = [
        _completion(core),
        _completion(bad),
    ]
    with pytest.raises(GenerationFailed, match="Reviewer 观察不完整"):
        _generator()._generate_legacy(_request(frame))
    assert len(FakeClient.requests) == 2


def test_reviewer_cannot_claim_coverage_with_only_a_partial_target_span() -> None:
    frame = new_frame("general_observation", (), ())
    core = _core(frame)
    partial = _observations(
        core,
        frame,
        changes={"b-spoken": {"text_spans": ["两种在意"]}},
    )
    FakeClient.responses = [
        _completion(core),
        _completion(partial),
    ]
    with pytest.raises(GenerationFailed, match="Reviewer 观察不完整"):
        _generator()._generate_legacy(_request(frame))
    assert len(FakeClient.requests) == 2


def test_one_repair_replaces_whole_block_and_all_linked_scenes_then_rereviews() -> None:
    frame = new_frame("general_observation", (), ())
    core = _core(frame)
    bad = _observations(
        core,
        frame,
        changes={
            "b-spoken": {
                "observation_type": "situated_event",
                "people": ["任何一方"],
                "relationships": ["两种在意"],
                "actions_or_events": ["写成反派"],
            }
        },
    )
    blocks = core["blocks"]
    scenes = core["scenes"]
    assert isinstance(blocks, list)
    assert isinstance(scenes, list)
    repaired_block = dict(
        next(block for block in blocks if isinstance(block, dict) and block["block_id"] == "b-spoken")
    )
    repaired_block["text"] = "边界不是结论，它只是让两种在意都有位置。"
    repaired_scene = dict(
        next(scene for scene in scenes if isinstance(scene, dict) and scene["scene_id"] == "s-spoken")
    )
    repaired_scene["action_text"] = "两条抽象线各自展开，最后保持一段留白。"
    repaired_core = {
        **core,
        "blocks": [
            repaired_block if block["block_id"] == "b-spoken" else block for block in blocks if isinstance(block, dict)
        ],
        "scenes": [
            repaired_scene if scene["scene_id"] == "s-spoken" else scene for scene in scenes if isinstance(scene, dict)
        ],
    }
    FakeClient.responses = [
        _completion(core),
        _completion(bad),
        _completion(
            {
                "blocks": [repaired_block],
                "scenes": [repaired_scene],
            }
        ),
        _completion(_observations(repaired_core, frame)),
    ]
    artifact = _generator()._generate_legacy(_request(frame))
    assert repaired_block["text"] in artifact.body
    assert len(artifact.fact_repair_receipts) == 1
    prompts = _payload_prompts()
    assert len(prompts) == 4
    assert "必须完整替换的 blocks" in prompts[2]
    assert '"block_id": "b-spoken"' in prompts[2]
    assert '"scene_id": "s-spoken"' in prompts[2]
    assert "最终完整可见成品" in prompts[3]


def test_second_semantic_failure_closes_without_another_repair() -> None:
    frame = new_frame("general_observation", (), ())
    core = _core(frame)
    bad = _observations(
        core,
        frame,
        changes={
            "b-spoken": {
                "observation_type": "situated_event",
                "people": ["任何一方"],
                "relationships": ["两种在意"],
                "actions_or_events": ["写成反派"],
            }
        },
    )
    blocks = core["blocks"]
    scenes = core["scenes"]
    assert isinstance(blocks, list)
    assert isinstance(scenes, list)
    block = next(item for item in blocks if isinstance(item, dict) and item["block_id"] == "b-spoken")
    scene = next(item for item in scenes if isinstance(item, dict) and item["scene_id"] == "s-spoken")
    FakeClient.responses = [
        _completion(core),
        _completion(bad),
        _completion({"blocks": [block], "scenes": [scene]}),
        _completion(bad),
    ]
    with pytest.raises(
        GenerationFailed,
        match="无法在一次叙事块修复内满足",
    ):
        _generator()._generate_legacy(_request(frame))
    assert len(FakeClient.requests) == 4


def test_product_claims_are_exact_and_never_nearest_match() -> None:
    product = ProductFact(
        sku="ZX-C218",
        display_name="双面短外套",
        facts={
            "material": "棉混纺",
            "colors": ["雾蓝", "米白"],
            "sample_weight_m_grams": 620,
        },
    )
    claims = DeepSeekGenerator._registered_product_claims(product)
    assert "这件商品的型号是 ZX-C218。" in claims
    assert "双面短外套的材质是棉混纺。" in claims
    assert "双面短外套有雾蓝、米白这些已确认颜色。" in claims
    assert "双面短外套的M 码当前样衣重量是 620 克。" in claims
    fact_ids = tuple(record.fact_id for record in product_fact_records(product))
    frame = new_frame("general_observation", (), fact_ids)
    context = BoundaryContext.from_request(
        _request(frame, products=(product,)),
        frame,
    )
    assert not hasattr(DeepSeekGenerator, "_normalize_registered_product_claims")
    assert not hasattr(DeepSeekGenerator, "_bind_rejected_product_claims")
    assert {record.exact_text for record in context.fact_registry if record.fact_kind == "product"} == set(claims)


def test_route_and_transport_only_retry_429_or_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeClient.responses = [
        FakeResponse(429, {}, {"Retry-After": "0"}),
        _completion({"primary_value": "建立人格"}),
    ]
    monkeypatch.setattr("src.tool.llm_gateway.deepseek.time.sleep", lambda _: None)
    result = _generator(max_retries=1).route(
        RoutingInput(
            "今天不知道发什么，帮我做条小红书。",
            _brand(),
            (),
        )
    )
    assert result == "brand_life_narrative"
    assert len(FakeClient.requests) == 2


def test_revision_must_change_allowed_expression_not_actuality() -> None:
    frame = new_frame(
        "actuality_reflection",
        ("今天店里忙了一天，回家还因为谁洗碗拌了两句。",),
        (),
    )
    core = _core(frame)
    first_request = _request(frame)
    FakeClient.responses = [
        _completion(core),
        _completion(_observations(core, frame)),
    ]
    first = _generator()._generate_legacy(first_request)
    FakeClient.responses = [
        _completion(core),
        _completion(_observations(core, frame)),
    ]
    with pytest.raises(GenerationFailed, match="没有实质改变"):
        _generator()._generate_legacy(
            replace(
                first_request,
                revision_instruction="别讲道理，荒诞一点。",
                prior_saved_body=first.body,
            )
        )


def test_writer_prompt_keeps_private_steering_out_of_fact_sources() -> None:
    frame = new_frame("general_observation", (), ())
    request = replace(
        _request(frame),
        collaboration_note="我平时更喜欢先说结论，再给一个具体例子。",
    )
    context = BoundaryContext.from_request(request, frame)
    generator = _generator()
    skeleton = generator._narrative_skeleton(request, frame, context)
    prompt = generator._writer_prompt(request, frame, context, skeleton)
    assert request.collaboration_note in prompt
    assert "成品中不得出现它的原文、转述或对它的解释" in prompt
    assert all(request.collaboration_note not in description for _, description in context.constraint_registry)


def test_dual_track_writer_receives_only_deidentified_preassigned_units() -> None:
    request = _kernel_request()
    assert request.narrative_frame is not None
    raw = _kernel_writer()
    FakeClient.responses = [_completion(raw)]

    artifact = _generator().generate(request)

    assert artifact.completion_snapshot_patch is not None
    assert artifact.completion_snapshot_patch["delivery_compiler_version"] == DUAL_TRACK_DELIVERY_COMPILER_VERSION
    assert artifact.completion_snapshot_patch["writer_model"] == "deepseek-test"
    assert artifact.completion_snapshot_patch["version_authorization"] == ("deterministic-dual-track-v1")
    assert isinstance(artifact.completion_snapshot_patch["claim_inventory_v1"], list)
    kernel_snapshot = artifact.completion_snapshot_patch["creative_kernel_v2"]
    assert isinstance(kernel_snapshot, dict)
    assert kernel_snapshot["program_id"] == OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM_V2
    assert isinstance(artifact.production, GraphicProductionBundle)
    assert "假设有这样一幕：" in artifact.production.full_body
    prompts = _payload_prompts()
    assert len(prompts) == 1
    writer_prompt = prompts[0]
    assert request.brand.brand_name not in writer_prompt
    assert request.brand.organization_name not in writer_prompt
    assert request.brand.account_name not in writer_prompt
    assert request.brand.positioning not in writer_prompt
    assert request.brand.decision_order not in writer_prompt
    assert request.brand.tone not in writer_prompt
    assert request.brand.content_role_boundary in writer_prompt
    assert request.brand.audience_description in writer_prompt
    assert request.active_domain_assets[0].body not in writer_prompt
    assert "resource:original_composition" not in writer_prompt
    assert '"unit_id"' in writer_prompt
    assert '"text"' in writer_prompt
    assert '"unit_id": "unit:natural-guide"' not in writer_prompt
    assert '"unit_id": "unit:release-caption"' not in writer_prompt
    assert "自然导读和发布配文由 DeliveryCompiler" in writer_prompt
    assert '"block_id"' not in writer_prompt
    assert '"fact_refs"' not in writer_prompt
    assert '"track": "creative_expression"' in writer_prompt
    assert '"mode": "hypothesis"' in writer_prompt
    assert "Reviewer" not in writer_prompt
    assert "服务端商品事实选择状态" in writer_prompt
    assert "正文始终由服务端原样插入" in writer_prompt
    assert "unit:natural-guide" not in writer_prompt
    assert "unit:release-caption" not in writer_prompt
    assert "reviewer_model" not in artifact.completion_snapshot_patch


def test_writer_full_paragraph_block_repetition_is_repaired_once() -> None:
    request = _kernel_request()
    paragraph_block = "先承认彼此的位置。\n\n再说明可以怎样回应。\n\n先承认彼此的位置。\n\n再说明可以怎样回应。"
    raw = _kernel_writer(body=paragraph_block)
    repaired_text = "先承认彼此的位置。\n\n再说明可以怎样回应，并把选择留给对方。"
    FakeClient.responses = [
        _completion(raw),
        _completion(
            {
                "units": [
                    {
                        "unit_id": "unit:body-opening",
                        "text": repaired_text,
                    }
                ]
            }
        ),
    ]

    artifact = _generator().generate(request)

    assert len(FakeClient.requests) == 2
    assert artifact.completion_snapshot_patch is not None
    kernel_document = artifact.completion_snapshot_patch["creative_kernel_v2"]
    assert isinstance(kernel_document, dict)
    units = kernel_document["units"]
    assert isinstance(units, list)
    repaired_unit = next(
        unit for unit in units if isinstance(unit, dict) and unit.get("unit_id") == "unit:body-opening"
    )
    assert repaired_unit["text"] == repaired_text
    assert "逐段完全相同的重复块" in _payload_prompts()[1]


def test_writer_repetition_repair_fails_closed_when_repeated_block_remains() -> None:
    request = _kernel_request()
    repeated = "第一段。\n\n第二段。\n\n第一段。\n\n第二段。"
    raw = _kernel_writer(body=repeated)
    FakeClient.responses = [
        _completion(raw),
        _completion(
            {
                "units": [
                    {
                        "unit_id": "unit:body-opening",
                        "text": "新的第一段。\n\n新的第二段。\n\n新的第一段。\n\n新的第二段。",
                    }
                ]
            }
        ),
    ]

    with pytest.raises(GenerationFailed, match="重复正文无法在一次"):
        _generator().generate(request)

    assert len(FakeClient.requests) == 2


def test_account_link_binding_ignores_only_presentation_whitespace() -> None:
    spaced = DeepSeekGenerator._account_link_match_view("品牌官方 / 品牌定义者")
    compact = DeepSeekGenerator._account_link_match_view("品牌官方/品牌定义者")

    assert spaced == compact
    assert spaced != DeepSeekGenerator._account_link_match_view("品牌官方／品牌定义者")


def test_ui12_writer_cannot_return_compiler_owned_visible_fields() -> None:
    request = _kernel_request()
    raw = _kernel_writer()
    units = raw["units"]
    assert isinstance(units, list)
    units.append(
        {
            "unit_id": "unit:release-caption",
            "text": "把问题场景带进评论区。",
        }
    )
    FakeClient.responses = [_completion(raw)]

    with pytest.raises(
        GenerationFailed,
        match="CreativeKernelV1 Writer 返回格式不完整",
    ):
        _generator().generate(request)

    assert len(FakeClient.requests) == 1


def test_writer_owns_audience_topic_when_user_has_not_supplied_one() -> None:
    missing_topic = "今天不知道发什么，帮我做条小红书。"
    request = replace(
        _kernel_request(),
        weak_seed=missing_topic,
        creative_plan=build_creative_plan(
            topic_spans=(missing_topic,),
            primary_value="brand_life_narrative",
            tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
            mechanism_id=None,
            target_shape="xiaohongshu_graphic:graphic",
            topic_origin="system_selected",
        ),
    )
    prompt = _generator()._kernel_writer_prompt(
        request,
        _parsed_kernel(request, _kernel_writer()),
    )

    assert '"topic_origin": "system_selected"' in prompt
    assert '"user_request_is_topic_evidence": false' in prompt
    assert missing_topic not in prompt
    assert "topic_spans 是用户原话证据" in prompt
    assert "若其中没有面向受众的实际题材" in prompt
    assert "自主选择一个安全、可直接发布的生活观察主线" in prompt
    assert "不得把“如何找选题、如何发内容、缺少\n灵感”本身写成" in prompt


def test_writer_natural_guide_has_distinct_graphic_and_video_responsibilities() -> None:
    graphic_request = _kernel_request()
    assert graphic_request.narrative_frame is not None
    assert graphic_request.creative_plan is not None
    graphic_context = BoundaryContext.from_request(
        graphic_request,
        graphic_request.narrative_frame,
    )
    graphic_skeleton = build_kernel_skeleton(
        frame=graphic_request.narrative_frame,
        fact_registry=graphic_context.fact_registry,
        constraint_refs=tuple(graphic_context.constraint_ids),
        program_id=select_kernel_program(frame=graphic_request.narrative_frame),
        media_format="graphic",
        kernel_version=KERNEL_VERSION,
        primary_product=graphic_request.primary_product,
    )
    video_request = replace(
        graphic_request,
        target="douyin_video",
        media_format="video",
        platform_direction=direction_for("douyin_video"),
        creative_plan=replace(
            graphic_request.creative_plan,
            platform_shape="douyin_video:video",
        ),
        brand=replace(
            graphic_request.brand,
            platform="抖音",
            media_format="视频",
        ),
    )
    video_skeleton = build_kernel_skeleton(
        frame=graphic_request.narrative_frame,
        fact_registry=graphic_context.fact_registry,
        constraint_refs=tuple(graphic_context.constraint_ids),
        program_id=select_kernel_program(frame=graphic_request.narrative_frame),
        media_format="video",
        kernel_version=KERNEL_VERSION,
        primary_product=video_request.primary_product,
    )

    graphic_prompt = _generator()._kernel_writer_prompt(
        graphic_request,
        graphic_skeleton,
        {},
    )
    video_prompt = _generator()._kernel_writer_prompt(
        video_request,
        video_skeleton,
        {},
    )

    assert "沿首图和不可交换的图序" in graphic_prompt
    assert "从首帧、时间推进到收束" not in graphic_prompt
    assert "适合停留阅读和收藏" in graphic_prompt
    assert "口语化转折或即时悬念" not in graphic_prompt
    assert "从首帧、时间推进到收束" in video_prompt
    assert "沿首图和不可交换的图序" not in video_prompt
    assert "口语化转折或即时悬念" in video_prompt
    assert "适合停留阅读和收藏" not in video_prompt


def test_creative_plan_v3_freezes_topic_origin_and_reads_v2_without_upgrade() -> None:
    current = build_creative_plan(
        topic_spans=("今天不知道发什么",),
        primary_value="brand_life_narrative",
        tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
        mechanism_id=None,
        target_shape="xiaohongshu_graphic:graphic",
        topic_origin="system_selected",
    )
    assert current.plan_version == PLAN_VERSION
    assert creative_plan_from_document(creative_plan_document(current)) == current

    legacy = build_creative_plan(
        topic_spans=("婆媳主题",),
        primary_value="brand_life_narrative",
        tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
        mechanism_id=None,
        target_shape="xiaohongshu_graphic:graphic",
        plan_version=LEGACY_PLAN_VERSION,
    )
    legacy_document = creative_plan_document(legacy)
    assert "topic_origin" not in legacy_document
    assert creative_plan_from_document(legacy_document) == legacy


def test_v3_copy_guard_applies_to_non_p3_publication_constraints() -> None:
    publication_sentence = "笛语服饰提供日常选择内容，并把最终判断留给受众"
    request = replace(
        _kernel_request(),
        primary_product="dressing_decision",
        brand=replace(
            _brand(),
            expression_constraint_context=(publication_sentence,),
        ),
    )
    kernel = _parsed_kernel(
        request,
        _kernel_writer(body=publication_sentence),
    )
    kernel = replace(kernel, kernel_version=KERNEL_VERSION)

    assert DeepSeekGenerator._copied_account_profile_units(request, kernel)


def test_dramatization_writer_receives_a_complete_scene_requirement() -> None:
    frame = new_frame("dramatization", (), ())
    request = _kernel_request(frame)
    skeleton = build_kernel_skeleton(
        frame=frame,
        fact_registry=(),
        constraint_refs=(),
        program_id=select_kernel_program(frame=frame),
        allowed_resource_ids=("resource:original_composition",),
    )

    prompt = _generator()._kernel_writer_prompt(request, skeleton)

    assert '"mode": "disclosed_dramatization"' in prompt
    assert "包含场景推进、角色行动或对白以及可见收束" in prompt
    assert "不能写成观点文章" in prompt


def test_ui10_frame_allowed_brand_fact_uses_service_frozen_unit() -> None:
    exact_fact = "笛语确认本账号只发布人工终审后的草稿。"
    fact = brand_fact_records((exact_fact,))[0]
    frame = new_frame(
        "general_observation",
        (),
        (),
        (fact.fact_id,),
    )
    request = replace(
        _kernel_request(frame),
        brand=replace(
            _brand(),
            brand_reference_context=(exact_fact,),
        ),
    )
    raw = _kernel_writer(
        body="这篇更想聊创作边界。",
        observation_only=True,
    )
    kernel = _parsed_kernel(request, raw)
    FakeClient.responses = [_completion(raw)]

    artifact = _generator().generate(request)

    assert exact_fact in artifact.production.full_body  # type: ignore[union-attr]
    assert kernel.unit("unit:frozen-fact:1").fact_refs == (fact.fact_id,)
    prompts = _payload_prompts()
    assert exact_fact not in prompts[0]
    assert len(prompts) == 1


def test_ui10_unresolved_brand_fact_fails_before_writer() -> None:
    request = _kernel_request(
        new_frame(
            "general_observation",
            (),
            (),
            ("fact:brand:not-currently-resolvable",),
        )
    )

    with pytest.raises(
        GenerationFailed,
        match="冻结事实标识无法解析",
    ):
        _generator().generate(request)

    assert FakeClient.requests == []


def test_ui09_writer_extra_production_field_fails_before_reviewer() -> None:
    request = _kernel_request()
    raw = _kernel_writer()
    units = raw["units"]
    assert isinstance(units, list)
    body = next(
        unit for unit in units if isinstance(unit, dict) and str(unit.get("unit_id", "")).startswith("unit:body")
    )
    assert isinstance(body, dict)
    body["production_note"] = "去厨房拍摄。"
    FakeClient.responses = [_completion(raw)]

    with pytest.raises(
        GenerationFailed,
        match="CreativeKernelV1 Writer 返回格式不完整",
    ):
        _generator().generate(request)

    assert len(FakeClient.requests) == 1


@pytest.mark.parametrize("drift", ("unknown", "omitted", "duplicate"))
def test_ui09_writer_unit_coverage_fails_closed(drift: str) -> None:
    request = _kernel_request()
    raw = _kernel_writer()
    units = raw["units"]
    assert isinstance(units, list)
    if drift == "unknown":
        units[0] = {"unit_id": "unit:invented", "text": "越界"}
    elif drift == "omitted":
        units.pop()
    else:
        units.append(dict(units[0]))
    FakeClient.responses = [_completion(raw)]

    with pytest.raises(
        GenerationFailed,
        match="CreativeKernelV1 Writer 返回格式不完整",
    ):
        _generator().generate(request)

    assert len(FakeClient.requests) == 1


def test_new_kernel_runtime_does_not_consume_external_reviewer_payload() -> None:
    request = _kernel_request()
    raw = _kernel_writer()
    FakeClient.responses = [
        _completion(raw),
        FakeResponse(500, {"error": "must remain unused"}),
    ]

    artifact = _generator().generate(request)

    assert len(FakeClient.requests) == 1
    assert len(FakeClient.responses) == 1
    assert artifact.completion_snapshot_patch is not None
    assert artifact.completion_snapshot_patch["version_authorization"] == ("deterministic-dual-track-v1")
    assert "reviewer_model" not in artifact.completion_snapshot_patch


def test_general_writer_text_is_compiled_inside_a_visible_non_fact_scope() -> None:
    request = _kernel_request()
    raw = _kernel_writer(
        body="饭桌上一句话让两个人都沉默。",
    )
    FakeClient.responses = [_completion(raw)]

    artifact = _generator().generate(request)

    assert isinstance(artifact.production, GraphicProductionBundle)
    assert "下面是创作性的生活观察，不对应真实人物或经历：饭桌上" in artifact.production.full_body
    assert len(FakeClient.requests) == 1


def test_revision_without_a_new_local_program_requires_changed_text() -> None:
    first_request = _kernel_request()
    raw = _kernel_writer()
    kernel = _parsed_kernel(first_request, raw)
    FakeClient.responses = [_completion(raw)]
    first = _generator().generate(first_request)
    assert first.completion_snapshot_patch is not None

    revision = _kernel_request(
        revision_instruction="第二段短一点。",
        prior_kernel=kernel,
    )
    FakeClient.responses = [_completion(raw)]
    with pytest.raises(GenerationFailed, match="没有实质改变"):
        _generator().generate(revision)
