from __future__ import annotations

import json
from dataclasses import replace
from typing import Any
from uuid import UUID

import httpx
import pytest

from src.brain.platform_directions import direction_for
from src.shared.closed_review import (
    CLOSED_REVIEW_TOOL_NAME,
    CLOSED_REVIEW_VERSION,
    build_closed_review_questions,
)
from src.shared.creative_kernel import (
    OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM_V2,
    CreativeKernelV1,
    build_kernel_skeleton,
    parse_writer_kernel,
    select_kernel_program,
)
from src.shared.creative_plan import (
    ACCOUNT_BASELINE_TONE_ID,
    build_creative_plan,
    creative_plan_document,
)
from src.shared.delivery_compiler import DELIVERY_COMPILER_VERSION
from src.shared.errors import GenerationFailed
from src.shared.factual_basis import brand_fact_records, product_fact_records
from src.shared.narrative import (
    NarrativeFrame,
    NarrativeIssue,
    new_frame,
    visible_digest,
)
from src.shared.review_evidence import (
    REVIEW_EVIDENCE_V2_VERSION,
    build_clause_contexts_v2,
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
    if isinstance(document, dict) and document.get("evidence_version") == REVIEW_EVIDENCE_V2_VERSION:
        return _strict_tool_completion(document, tokens=tokens)
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


def _intake_plan(message: str) -> dict[str, object]:
    return creative_plan_document(
        build_creative_plan(
            topic_spans=(message,),
            primary_value="brand_life_narrative",
            tone_ids=(ACCOUNT_BASELINE_TONE_ID,),
            mechanism_id=None,
            target_shape="xiaohongshu_graphic:graphic",
        )
    )


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
        delivery_compiler_version=DELIVERY_COMPILER_VERSION,
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
            {
                "unit_id": "unit:natural-guide",
                "text": "从不同位置看同一段关系，先保留理解的余地。",
            },
            *body_units,
            {
                "unit_id": "unit:release-caption",
                "text": "尊重差异，也保留自己的边界。",
            },
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
    return parse_writer_kernel(raw, skeleton)


def test_kernel_writer_prompt_exposes_current_trusted_contracts() -> None:
    request = _kernel_request()
    prompt = _generator()._kernel_writer_prompt(
        request,
        _parsed_kernel(request, _kernel_writer()),
    )

    assert "recommendation 必须用清楚可见的建议、" in prompt
    assert "recommendation unit 中每个可独立切分的 clause 都必须有" in prompt
    assert "不能写具体时间、地点、对白、情境例子或没有语态" in prompt
    assert '"unit_id": "unit:body-closing"' in prompt
    assert '"unit_contract": "abstract_observation"' in prompt
    assert "Writer-owned clause 不得让当前表达者或第一人称复数承担" in prompt
    assert "abstract_observation\n只写状态、判断、关系理解或比喻" in prompt
    assert "actuality_reflection 对应的用户现实原文" in prompt
    assert "Writer 只能写不复述该事实的抽象关系反思" in prompt
    assert "不能复制、概括或扩写人物、动作、对白、动机、原因、结果" in prompt


def test_kernel_writer_prompt_exposes_read_only_product_packet_but_not_fact_authorship() -> None:
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

    prompt = _generator()._kernel_writer_prompt(request, skeleton)

    assert "双面短外套的材质是棉混纺。" in prompt
    assert "双面短外套的M 码当前样衣重量是 620 克。" in prompt
    assert "ProductFactPacket" in prompt
    assert "ImmutableFactBlock" in prompt
    assert "只能引用 fact_block_id；正文由服务端原样插入" in prompt
    assert "claim_refs 只是\n审查线索" in prompt
    assert "不能把硬属性、数字或 canonical_text" in prompt
    assert "首次最多选择 3 个" in prompt
    assert '"entity_kind": "apparel_product"' in prompt
    assert any(
        unit.purpose == "frozen_fact" and unit.text == "双面短外套的材质是棉混纺。" for unit in skeleton.units
    )


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
    selected = tuple(
        block.fact_block_id
        for block in context.product_fact_blocks[:2]
    )
    violating_text = "双面短外套的材质是棉混纺。"
    kernel = parse_writer_kernel(
        {
            "fact_block_refs": list(selected),
            "units": [
                {
                    "unit_id": unit.unit_id,
                    "text": (
                        violating_text
                        if unit.unit_id == "unit:body"
                        else "先看清楚，再保留选择。"
                    ),
                    "claim_refs": [
                        context.product_fact_blocks[0].fact_id
                    ],
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
    assert "判断对象只能是泛指读者如何看、如何选、如何保留自己的判断" in prompt
    assert "claim_refs 必须\n是空数组" in prompt
    assert '"unit_contract": "audience_guidance"' in prompt
    assert "只写一至两句与已插入事实配套的观看回报" in prompt
    assert "不得因为 purpose 或写作习惯换成建议、假设、演绎" in prompt
    assert "只谈读者如何看、如何选、如何保留判断" in prompt
    assert "不得输出“抽象原则”等内部合同语言" in prompt
    assert "不得成为创意文字的主语、宾语或指代对象" in prompt
    assert "所有文字必须在不知道底层对象名称、类别" in prompt
    assert "和任何属性时仍然成立" in prompt
    assert "使用自然第二人称直接和受众说话" in prompt
    assert "body 用二至四个短 clause" in prompt
    assert "release_caption 留下一个可以直接回答" in prompt
    assert "xiaohongshu_graphic / graphic" in prompt
    assert "真实、克制、有依据" in prompt


def test_product_fact_ownership_repair_rewrites_one_coherent_creative_set() -> None:
    product = ProductFact(
        sku="ZX-C218",
        display_name="双面短外套",
        facts={
            "entity_kind": "apparel_product",
            "colors": ["炭灰纯色", "深绿细格纹"],
        },
    )
    fact_ids = tuple(
        record.fact_id
        for record in product_fact_records(product)
    )
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
    selected = tuple(
        block.fact_block_id
        for block in context.product_fact_blocks[:2]
    )
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

    assert affected == frozenset(
        unit.unit_id
        for unit in kernel.writable_units
    )


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
        if question.dimension == "statement_mode":
            mode_by_contract = {
                "abstract_observation": "generic_observation",
                "audience_guidance": "generic_observation",
                "recommendation": "recommendation",
                "hypothetical_example": "hypothesis",
                "disclosed_dramatization": "dramatization",
                "actuality_reflection": "generic_observation",
            }
            status = "present"
            quote = question.exact_text
            operands = [mode_by_contract[clause_context.unit_contract]]
        elif is_event:
            status = "present"
            quote = question.exact_text
            operands = ["event"]
        else:
            status = "absent"
            quote = ""
            operands = []
        if clause_context.unit_id in partial and question.dimension == "statement_mode":
            quote = question.exact_text[: max(1, len(question.exact_text) // 2)]
        answers.append(
            {
                "question_id": question.question_id,
                "status": status,
                "quote": quote,
                "operands": operands,
            }
        )
    return {
        "evidence_version": CLOSED_REVIEW_VERSION,
        "answers": answers,
    }


def test_conversation_intake_preserves_exact_spans_and_mode() -> None:
    message = "今天店里忙了一天，回家还因为谁洗碗拌了两句。帮我发条小红书。"
    FakeClient.responses = [
        _completion(
            {
                "kind": "ready",
                "message": "好，我保留这段原话，其他由我来完成。",
                "user_premises": [message],
                "user_fact_spans": ["今天店里忙了一天，回家还因为谁洗碗拌了两句。"],
                "narrative_mode": "actuality_reflection",
                "creative_plan": _intake_plan(message),
            }
        )
    ]
    decision = _generator().collaborate(
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
    assert decision.disposition == "ready"
    assert decision.user_premises == (message,)
    assert decision.user_fact_spans == ("今天店里忙了一天，回家还因为谁洗碗拌了两句。",)
    assert decision.narrative_mode == "actuality_reflection"


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
    mode: str,
    facts: list[str],
) -> None:
    FakeClient.responses = [
        _completion(
            {
                "kind": "ready",
                "message": "可以，直接开始。",
                "user_premises": [message],
                "user_fact_spans": facts,
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
            explicit_narrative_mode=("dramatization" if mode == "dramatization" else None),
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
        )
    )
    assert decision.disposition == "question"
    assert "具体发生" in decision.message


def test_conversation_rejects_synthetic_or_mode_drifted_spans() -> None:
    message = "帮我写条婆媳主题的小红书。"
    FakeClient.responses = [
        _completion(
            {
                "kind": "ready",
                "message": "开始。",
                "user_premises": [message],
                "user_fact_spans": ["婆婆曾经带过孩子"],
                "narrative_mode": "actuality_reflection",
                "creative_plan": _intake_plan(message),
            }
        )
    ]
    with pytest.raises(GenerationFailed, match="事实跨度不存在"):
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
        _generator().generate(request)


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
    artifact = _generator().generate(request)
    assert isinstance(artifact.production, GraphicProductionBundle)
    assert artifact.reviewed_digest == visible_digest(artifact.outline, artifact.body)
    for fact in frame.user_facts:
        assert fact.exact_text in artifact.body
    assert artifact.provider_usage == {"total_tokens": 150}
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
        _generator().generate(_request(frame))
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
        _generator().generate(_request(frame))
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
    artifact = _generator().generate(_request(frame))
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
        _generator().generate(_request(frame))
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
    first = _generator().generate(first_request)
    FakeClient.responses = [
        _completion(core),
        _completion(_observations(core, frame)),
    ]
    with pytest.raises(GenerationFailed, match="没有实质改变"):
        _generator().generate(
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


def test_ui09_writer_receives_only_deidentified_kernel_inputs() -> None:
    request = _kernel_request()
    raw = _kernel_writer()
    kernel = _parsed_kernel(request, raw)
    FakeClient.responses = [
        _completion(raw),
        _completion(_kernel_observations(kernel, request=request)),
    ]

    artifact = _generator().generate(request)

    assert artifact.completion_snapshot_patch is not None
    assert artifact.completion_snapshot_patch["delivery_compiler_version"] == DELIVERY_COMPILER_VERSION
    assert artifact.completion_snapshot_patch["review_evidence_version"] == REVIEW_EVIDENCE_V2_VERSION
    assert artifact.completion_snapshot_patch["closed_review_contract"] == "closed-review-questions-v1"
    assert isinstance(artifact.completion_snapshot_patch["claim_inventory_v1"], list)
    kernel_snapshot = artifact.completion_snapshot_patch["creative_kernel_v1"]
    clause_context = artifact.completion_snapshot_patch["clause_context_v2"]
    assert isinstance(clause_context, list)
    assert any(
        isinstance(item, dict)
        and item["text_source"] == "server_wrapper"
        and item["unit_contract"] == "hypothetical_example"
        for item in clause_context
    )
    assert isinstance(kernel_snapshot, dict)
    assert kernel_snapshot["program_id"] == OBSERVATION_WITH_HYPOTHETICAL_EXAMPLE_PROGRAM_V2
    assert isinstance(artifact.production, GraphicProductionBundle)
    assert artifact.production.full_body == "\n\n".join(unit.text for unit in kernel.units if unit.purpose == "body")
    prompts = _payload_prompts()
    assert len(prompts) == 2
    writer_prompt = prompts[0]
    assert request.brand.brand_name not in writer_prompt
    assert request.brand.organization_name not in writer_prompt
    assert request.brand.account_name not in writer_prompt
    assert request.active_domain_assets[0].body not in writer_prompt
    assert "resource:original_composition" not in writer_prompt
    assert '"unit_id"' in writer_prompt
    assert '"text"' in writer_prompt
    assert '"block_id"' not in writer_prompt
    assert '"fact_refs"' not in writer_prompt
    reviewer_prompt = prompts[1]
    assert '"evidence_version":"review-evidence-v2"' in reviewer_prompt
    assert "每个固定风险问题恰好" in reviewer_prompt
    assert '"question_id"' in reviewer_prompt
    assert '"status":"present"' in reviewer_prompt
    assert "motive_or_mental_state" in reviewer_prompt
    assert "statement_mode" in reviewer_prompt
    assert '"exact_text"' in reviewer_prompt
    assert '"allowed_quotes"' not in reviewer_prompt
    assert "可以跨越 clause\n  内部标点" in reviewer_prompt
    assert "最短唯一连续片段" in reviewer_prompt
    assert "绝不能把中文弯引号改成 JSON" in reviewer_prompt
    assert "U+0022" in reviewer_prompt
    assert "不能通过省略整个问题表达 absent" in reviewer_prompt
    assert "面向不特定受众的第二人称阅读邀请" in reviewer_prompt
    assert "文章向不特定读者提供观看回报" in reviewer_prompt
    assert '"occurrence"' not in reviewer_prompt
    assert '"start"' not in reviewer_prompt
    assert '"end"' not in reviewer_prompt


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
    FakeClient.responses = [
        _completion(raw),
        _completion(_kernel_observations(kernel, request=request)),
    ]

    artifact = _generator().generate(request)

    assert exact_fact in artifact.production.full_body  # type: ignore[union-attr]
    assert kernel.unit("unit:frozen-fact:1").fact_refs == (fact.fact_id,)
    prompts = _payload_prompts()
    assert exact_fact not in prompts[0]
    assert exact_fact not in prompts[1]


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
    body = units[2]
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


def test_ui09_reviewer_must_cover_exact_complete_units() -> None:
    request = _kernel_request()
    raw = _kernel_writer()
    kernel = _parsed_kernel(request, raw)
    FakeClient.responses = [
        _completion(raw),
        _completion(
            _kernel_observations(
                kernel,
                omit=frozenset({"unit:title"}),
                partial=frozenset({"unit:body-opening"}),
            )
        ),
    ]

    with pytest.raises(
        GenerationFailed,
        match="Reviewer 闭合证据",
    ):
        _generator().generate(request)

    assert len(FakeClient.requests) == 2


@pytest.mark.parametrize(
    "mutation",
    ("missing", "duplicate", "extra", "partial", "fake_span", "uncertain"),
)
def test_ui10_evidence_failure_never_calls_writer_repair(
    mutation: str,
) -> None:
    request = _kernel_request()
    raw = _kernel_writer()
    kernel = _parsed_kernel(request, raw)
    document = _kernel_observations(kernel)
    answers = document["answers"]
    assert isinstance(answers, list)
    if mutation == "missing":
        answers.pop()
    elif mutation == "duplicate":
        answers.append(dict(answers[0]))
    elif mutation == "extra":
        extra = dict(answers[0])
        extra["question_id"] = "unit:extra:clause:1:risk:subject_binding"
        answers.append(extra)
    elif mutation == "partial":
        answers[-2] = dict(answers[-2])
        answers[-2]["quote"] = "部分"
    elif mutation == "fake_span":
        answers[-2] = dict(answers[-2])
        answers[-2]["quote"] = "并不存在的谓词"
    else:
        answers[-2] = dict(answers[-2])
        answers[-2]["status"] = "uncertain"
        answers[-2]["quote"] = ""
        answers[-2]["operands"] = []
    FakeClient.responses = [
        _completion(raw),
        _completion(document),
    ]

    with pytest.raises(
        GenerationFailed,
        match="Reviewer 闭合证据|Reviewer 证据",
    ):
        _generator().generate(request)

    assert len(FakeClient.requests) == 2


def test_ui09_allows_only_one_affected_unit_repair_and_full_rereview() -> None:
    request = _kernel_request()
    first_raw = _kernel_writer(
        body="饭桌上一句话让两个人都沉默。",
    )
    first_kernel = _parsed_kernel(request, first_raw)
    repair_raw = {
        "units": [
            {
                "unit_id": "unit:body-opening",
                "text": "换位思考不等于没有边界。",
            }
        ]
    }
    repaired_kernel = replace(
        first_kernel,
        units=tuple(
            replace(unit, text="换位思考不等于没有边界。") if unit.unit_id == "unit:body-opening" else unit
            for unit in first_kernel.units
        ),
    )
    FakeClient.responses = [
        _completion(first_raw),
        _completion(
            _kernel_observations(
                first_kernel,
                body_type="situated_event",
            )
        ),
        _completion(repair_raw),
        _completion(_kernel_observations(repaired_kernel)),
    ]

    artifact = _generator().generate(request)

    assert "换位思考不等于没有边界。" in artifact.production.full_body  # type: ignore[union-attr]
    assert len(FakeClient.requests) == 4
    prompts = _payload_prompts()
    assert "unit:body-opening" in prompts[2]
    assert "unit:title" not in prompts[2]
    assert "服务端 writer-owned clause" in prompts[3]


def test_ui09_second_review_failure_stops_without_another_repair() -> None:
    request = _kernel_request()
    first_raw = _kernel_writer(
        body="饭桌上一句话让两个人都沉默。",
    )
    first_kernel = _parsed_kernel(request, first_raw)
    repair_raw = {
        "units": [
            {
                "unit_id": "unit:body-opening",
                "text": "门关上以后，谁都没有再说话。",
            }
        ]
    }
    repaired_kernel = replace(
        first_kernel,
        units=tuple(
            replace(unit, text="门关上以后，谁都没有再说话。") if unit.unit_id == "unit:body-opening" else unit
            for unit in first_kernel.units
        ),
    )
    FakeClient.responses = [
        _completion(first_raw),
        _completion(
            _kernel_observations(
                first_kernel,
                body_type="situated_event",
            )
        ),
        _completion(repair_raw),
        _completion(
            _kernel_observations(
                repaired_kernel,
                body_type="situated_event",
            )
        ),
    ]

    with pytest.raises(
        GenerationFailed,
        match="无法在一次 CreativeKernel unit 修复内满足",
    ):
        _generator().generate(request)

    assert len(FakeClient.requests) == 4


def test_ui09_revision_requires_changed_writable_kernel() -> None:
    first_request = _kernel_request()
    raw = _kernel_writer()
    kernel = _parsed_kernel(first_request, raw)
    FakeClient.responses = [
        _completion(raw),
        _completion(_kernel_observations(kernel)),
    ]
    first = _generator().generate(first_request)
    assert first.completion_snapshot_patch is not None

    revision = _kernel_request(
        revision_instruction="别讲道理，荒诞一点。",
        prior_kernel=kernel,
    )
    FakeClient.responses = [
        _completion(raw),
        _completion(_kernel_observations(kernel)),
    ]
    with pytest.raises(GenerationFailed, match="没有实质改变"):
        _generator().generate(revision)
