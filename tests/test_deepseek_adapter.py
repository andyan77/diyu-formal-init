from __future__ import annotations

import json
import time
from dataclasses import replace
from typing import Any, cast
from uuid import UUID

import httpx
import pytest

from src.brain.platform_directions import direction_for
from src.shared.errors import GenerationFailed
from src.shared.types import (
    ActiveAsset,
    BrandContext,
    ContentProductionBundle,
    ContentSemanticContract,
    ConversationInput,
    ConversationTurn,
    GenerationInput,
    GraphicProductionBundle,
    ProductFact,
    RoutingInput,
    VideoProductionBundle,
)
from src.tool.llm_gateway.deepseek import (
    BoundaryContext,
    ContentCore,
    DeepSeekGenerator,
    UnitIssue,
)


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


@pytest.fixture()
def generation_input() -> GenerationInput:
    return GenerationInput(
        run_id=UUID("00000000-0000-0000-0000-000000000101"),
        task_id=UUID("00000000-0000-0000-0000-000000000102"),
        weak_seed="一家人一定要穿成同款，才算有家庭感吗？",
        primary_product="dressing_decision",
        revision_instruction=None,
        brand=BrandContext(
            "笛语服饰",
            "家庭成员各自成立，也可以自然呼应",
            "先尊重差异，再讨论呼应",
            "真实、克制、有依据",
            "笛语服饰品牌官方账号",
            "当前运营者",
            "笛语服饰",
            "品牌官方 / 品牌定义者",
            "表达品牌判断，不冒充自然人、门店岗位或顾客。",
            "重视真实感受与家庭差异的人。",
            "brand-expression-v1",
            "抖音",
            "视频",
            "使用创作者表达与本次原创抽象构成，不默认现实物品、场地或既有素材。",
        ),
        target="douyin_video",
        media_format="video",
        platform_direction=direction_for("douyin_video"),
        active_domain_assets=(
            ActiveAsset(
                "B-001",
                "v1",
                "brand",
                "品牌基线",
                "内容先建立理解和关系，不把生活强行变成卖货。",
            ),
        ),
    )


def _with(request: GenerationInput, **changes: object) -> GenerationInput:
    return GenerationInput(**{**request.__dict__, **changes})


def _claim(
    claim_id: str,
    slot: str,
    text: str,
    basis: str = "brand_viewpoint",
    actuality: str = "non_event",
    source_refs: tuple[str, ...] = ("source:brand_baseline",),
) -> dict[str, object]:
    return {
        "claim_id": claim_id,
        "slot": slot,
        "text": text,
        "basis": basis,
        "actuality": actuality,
        "source_refs": list(source_refs),
    }


def _step(
    step_id: str,
    purpose: str,
    action_text: str,
    claim_refs: tuple[str, ...],
    actor_refs: tuple[str, ...] = (),
    resource_refs: tuple[str, ...] = (),
    sound_text: str = "",
    production_note: str = "",
) -> dict[str, object]:
    return {
        "step_id": step_id,
        "purpose": purpose,
        "actor_refs": list(actor_refs),
        "resource_refs": list(resource_refs),
        "action_text": action_text,
        "sound_text": sound_text,
        "production_note": production_note,
        "claim_refs": list(claim_refs),
    }


def _video_core(
    claims: list[dict[str, object]] | None = None,
    spoken_order: list[str] | None = None,
    steps: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "speaker_ref": "speaker:brand_account",
        "claims": claims
        if claims is not None
        else [
            _claim("c1", "title", "不必穿成同款"),
            _claim(
                "c2", "natural_guide", "从同款是否等于家庭感进入", "user_premise", "non_event", ("source:user_request",)
            ),
            _claim("c3", "viewing_flow", "让两组独立构成在结尾形成呼应", "conditional_guidance", "non_event"),
            _claim("c4", "release_caption", "你更在意整齐，还是每个人都自在？"),
            _claim("c5", "choice", "先保留每个人舒服的选择", "conditional_guidance", "hypothetical"),
            _claim("c6", "boundary", "如果需要正式合照，再找一个自然呼应点", "conditional_guidance", "hypothetical"),
            _claim("c7", "next_action", "先看每个人愿不愿意这样穿", "conditional_guidance", "hypothetical"),
            _claim("c8", "spoken", "一家人的家庭感，不一定来自穿成同款。"),
            _claim(
                "c9",
                "spoken",
                "我们更愿意先尊重每个人舒服的选择，再找一个自然的呼应点。",
            ),
        ],
        "spoken_order": spoken_order if spoken_order is not None else ["c8", "c9"],
        "scene_steps": steps
        if steps is not None
        else [
            _step(
                "s1",
                "cover",
                "两组不同形状围住标题“不必穿成同款”。",
                ("c1",),
                resource_refs=("resource:original_composition",),
            ),
            _step(
                "s2",
                "scene",
                "当前创作者自然口播，两组形状各自移动后保留呼应间距。",
                ("c8", "c9"),
                actor_refs=("actor:creator",),
                resource_refs=("resource:creator_expression", "resource:original_composition"),
                sound_text="当前创作者人声，结尾留半拍安静。",
            ),
        ],
    }


def _completion(content: str, tokens: int = 0) -> FakeResponse:
    payload: dict[str, Any] = {"choices": [{"message": {"content": content}}]}
    if tokens:
        payload["usage"] = {"total_tokens": tokens}
    return FakeResponse(200, payload)


def _core_response(core: dict[str, object], tokens: int = 0) -> FakeResponse:
    return _completion(json.dumps(core, ensure_ascii=False), tokens)


def _unit_ids(core: dict[str, object]) -> list[str]:
    claims = core["claims"]
    steps = core["scene_steps"]
    assert isinstance(claims, list) and isinstance(steps, list)
    return [str(entry["claim_id"]) for entry in claims] + [str(entry["step_id"]) for entry in steps]


def _verdicts(
    core: dict[str, object],
    failures: dict[str, tuple[str, ...]] | None = None,
) -> FakeResponse:
    failures = failures or {}
    verdicts = []
    for unit_id in _unit_ids(core):
        entry: dict[str, object] = {"id": unit_id}
        for flag in (
            "identity_ok",
            "actuality_ok",
            "resource_ok",
            "fact_ok",
            "instruction_ok",
        ):
            entry[flag] = flag not in failures.get(unit_id, ())
        verdicts.append(entry)
    return _completion(json.dumps({"verdicts": verdicts}, ensure_ascii=False))


def _repairs(*units: dict[str, object]) -> FakeResponse:
    return _completion(json.dumps({"repairs": list(units)}, ensure_ascii=False))


def _install_fake(monkeypatch: pytest.MonkeyPatch, responses: list[FakeResponse]) -> None:
    FakeClient.responses = responses
    FakeClient.requests = []
    monkeypatch.setattr(httpx, "Client", FakeClient)


def _generator() -> DeepSeekGenerator:
    return DeepSeekGenerator(
        "https://compat.example/v1",
        "not-a-real-key",
        "verified-deepseek-model",
    )


def test_generation_prompt_separates_six_input_semantics(
    generation_input: GenerationInput,
) -> None:
    context = BoundaryContext.from_request(generation_input)
    prompt = DeepSeekGenerator._generation_prompt(generation_input, context)

    assert "task_topic_or_request" in prompt
    assert generation_input.weak_seed in prompt
    assert "不是用户亲历" in prompt
    assert "user_presented_actuality" in prompt
    assert "（本次没有。没有列出即为不存在，不得虚构。）" in prompt
    assert "brand_viewpoint" in prompt
    assert generation_input.brand.positioning in prompt
    assert "不证明品牌观察过、经历过或已经执行任何具体事件" in prompt
    assert "confirmed_actuality" in prompt
    assert "无已确认门店事实、无已执行服务、无顾客案例、无家庭事件、无既有照片或素材" in prompt
    assert "method_guidance" in prompt
    assert "不证明任何现实人物、物品、场地或素材存在" in prompt
    assert "allowed_speaker_and_resources" in prompt
    assert "不证明场地内存在家庭成员、顾客、商品、合照、家具或已执行服务" in prompt
    assert "speaker:brand_account" in prompt
    assert "actor:creator" in prompt
    assert "resource:creator_expression" in prompt
    assert "source:user_request" in prompt
    assert "只要点名当前商品的名称、品类、颜色、结构或可观察特征" in prompt
    assert "标题、观点、比喻、幽默、节奏、完整口播和互动由你自然创作" in prompt
    assert generation_input.platform_direction.direction in prompt
    assert generation_input.platform_direction.platform_capability_source_ref not in prompt
    assert generation_input.platform_direction.provenance.maintenance_owner not in prompt
    assert not any(
        source_ref in prompt
        for source_ref in generation_input.platform_direction.provenance.source_refs
    )
    assert "B-001" not in prompt
    assert "schema_version" not in prompt


def test_judgement_reads_the_complete_visible_candidate_before_unit_verdicts(
    generation_input: GenerationInput,
) -> None:
    generator = _generator()
    context = BoundaryContext.from_request(generation_input)
    core = generator._parse_core(generation_input, context, _video_core())

    prompt = DeepSeekGenerator._judgement_prompt(
        generation_input,
        context,
        core,
    )

    assert "候选按用户阅读/制作顺序展开后的完整可见成品" in prompt
    assert "一家人的家庭感，不一定来自穿成同款。" in prompt
    assert "一个单元单独看似" in prompt
    assert "不能把已知" in prompt and "重量类比" in prompt


def test_revision_prompt_applies_the_instruction_to_every_visible_unit(
    generation_input: GenerationInput,
) -> None:
    request = _with(
        generation_input,
        revision_instruction="不要使用桌子和纸笔。",
        prior_saved_body="旧稿仍安排了桌面字卡。",
    )
    prompt = DeepSeekGenerator._generation_prompt(
        request,
        BoundaryContext.from_request(request),
    )

    assert "修改要求约束全部可见单元" in prompt
    assert "画面动作、声音、制作提示和发布互动" in prompt
    assert "不能只改合同字段、摘要或时长标签" in prompt
    assert "仅供本次自然修改的当前旧稿" in prompt
    assert "它不是现实事实来源" in prompt
    assert "旧稿仍安排了桌面字卡" in prompt
    assert "冲突的创作和制作要求已被本次修改替代" in prompt
    assert "本次修改（当前最高优先级" in prompt
    assert "用“不要、不能、不得、只用”表达的硬边界也应静默遵守" in prompt
    assert "不得把这些后台约束逐项搬进正文、口播、字幕或制作提示" in prompt
    assert "发生可观察的实质变化" in prompt
    assert "不能只删一个无关短句" in prompt


def test_topic_only_life_content_forbids_invented_dialogue_and_possessions(
    generation_input: GenerationInput,
) -> None:
    request = _with(
        generation_input,
        weak_seed="写一条家庭关系主题的小红书。",
        user_actuality_quotes=(),
        products=(),
        system_creative_plan="用一般观察选择关系里的边界感作为主线。",
    )
    context = BoundaryContext.from_request(request)

    writer_prompt = DeepSeekGenerator._generation_prompt(request, context)
    core = _generator()._parse_core(request, context, _video_core())
    judge_prompt = DeepSeekGenerator._judgement_prompt(request, context, core)

    for prompt in (writer_prompt, judge_prompt):
        assert "具体对白" in prompt
        assert "个人" in prompt and "习惯" in prompt
        assert "即使" in prompt and ("假设" in prompt or "想象" in prompt)
        assert "本次没有登记商品" in prompt
        assert "穿着" in prompt and "具体衣物" in prompt


def test_repair_discards_an_experience_shell_instead_of_paraphrasing_it(
    generation_input: GenerationInput,
) -> None:
    request = _with(
        generation_input,
        weak_seed="写一条家庭关系主题的小红书。",
        user_actuality_quotes=(),
        products=(),
    )
    context = BoundaryContext.from_request(request)
    core = _generator()._parse_core(request, context, _video_core())

    prompt = DeepSeekGenerator._unit_repair_prompt(
        request,
        context,
        core,
        (
            UnitIssue(
                "c8",
                "invented_actuality",
                "这个账号最近一直在想一段家庭关系。",
            ),
        ),
    )

    assert "必须丢弃原句的经历外壳" in prompt
    assert "不能近义改写或换一个假想人物继续叙事" in prompt
    assert "本次话题对象 + 当前一般判断" in prompt
    assert "actuality 必须是" in prompt and "non_event" in prompt


def test_platform_recompile_keeps_source_but_demands_target_native_change(
    generation_input: GenerationInput,
) -> None:
    request = _with(
        generation_input,
        target="xiaohongshu_graphic",
        media_format="graphic",
        platform_direction=direction_for("xiaohongshu_graphic"),
        revision_instruction="另做小红书图文版。",
        prior_saved_body="源视频完整正文。",
        source_version_description="由抖音视频 V2 改编",
    )
    prompt = DeepSeekGenerator._generation_prompt(
        request,
        BoundaryContext.from_request(request),
    )

    assert "源视频完整正文" in prompt
    assert "标题和正文开头不得沿用源视频" in prompt
    assert "首图承诺、递进图序和可独立阅读的完整正文" in prompt
    assert "改变标题、开头、内容顺序、媒体组织、画面节奏" in prompt
    assert "不能只用 source:prior_version 承载商品事实或品牌立场" in prompt


def test_weak_seed_stays_topic_unless_product_requires_near_field_signal(
    generation_input: GenerationInput,
) -> None:
    topic_context = BoundaryContext.from_request(generation_input)
    near_field_context = BoundaryContext.from_request(_with(generation_input, primary_product="local_response"))

    assert topic_context.user_presented_actuality == ""
    assert topic_context.user_actuality_source is None
    assert "source:user_actuality" not in topic_context.source_ids
    assert near_field_context.user_actuality_source == "source:user_actuality"
    assert generation_input.weak_seed in near_field_context.user_presented_actuality


def test_synthetic_near_field_seed_stays_a_hypothetical_premise(
    generation_input: GenerationInput,
) -> None:
    request = _with(
        generation_input,
        primary_product="local_response",
        brand=replace(
            generation_input.brand,
            business_data_kind="synthetic_business_fixture",
        ),
    )
    context = BoundaryContext.from_request(request)

    assert context.user_presented_actuality == ""
    assert context.user_actuality_source is None
    assert "source:user_actuality" not in context.source_ids
    assert "只能作为假设情境和演示脚本起点" in context.task_topic_or_request
    assert "不得用第一人称" in context.task_topic_or_request


def test_synthetic_user_actuality_is_authorized_only_for_the_current_artifact(
    generation_input: GenerationInput,
) -> None:
    actuality = "今天店里忙了一天，回家还因为谁洗碗拌了两句。"
    request = _with(
        generation_input,
        weak_seed=f"{actuality}帮我发条小红书。",
        primary_product="local_response",
        user_actuality_quotes=(actuality,),
        brand=replace(
            generation_input.brand,
            business_data_kind="synthetic_business_fixture",
        ),
    )
    context = BoundaryContext.from_request(request)

    assert context.user_presented_actuality == f"用户原话：{actuality}"
    assert context.user_actuality_quotes == (actuality,)
    assert "可以作为本次内容作者明确提供的事实忠实使用或自然压缩" in (
        context.task_topic_or_request
    )
    assert "不证明现实账号、操作者或门店具有相应身份和履历" in (
        context.task_topic_or_request
    )
    assert "不得写入长期画像" in context.task_topic_or_request


def test_routing_prompt_describes_p5_by_general_audience_value(
    generation_input: GenerationInput,
) -> None:
    prompt = DeepSeekGenerator._routing_prompt(
        RoutingInput(
            weak_seed="让人从同一取景框里的画面变化看见新的穿着可能。",
            brand=generation_input.brand,
            products=(),
        )
    )

    assert "必须通过真实商品与画面变化" in prompt
    assert "同一个人、同一动作、两面" not in prompt
    assert "双面不等于一件顶两件" not in prompt


def test_conversation_prompt_makes_creative_judgement_the_systems_job(
    generation_input: GenerationInput,
) -> None:
    request = ConversationInput(
        message="今天不知道发什么，帮我做条小红书。",
        history=(),
        brand=generation_input.brand,
        products=(),
        target="xiaohongshu_graphic",
    )

    prompt = DeepSeekGenerator._conversation_prompt(request)

    assert "系统读取可信账号、品牌、平台、商品和系列上下文" in prompt
    assert "自主决定主题、观点、受众价值、切口、结构、风格和平台组织" in prompt
    assert "题材、观点、受众、角度、情绪、结构、是否升华" in prompt
    assert "user_premises" in prompt
    assert "user_actuality_quotes" in prompt
    assert "system_creative_plan" in prompt
    assert "missing_fact_kind" in prompt
    assert "missing_fact_basis" in prompt
    assert '"brief"' not in prompt


def test_collaborate_preserves_exact_premise_but_replaces_untrusted_model_plan(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    message = "今天店里忙了一天，回家还因为谁洗碗拌了两句。帮我发条小红书。"
    _install_fake(
        monkeypatch,
        [
            _completion(
                json.dumps(
                    {
                        "kind": "ready",
                        "message": "我先从两个人都很累，却把情绪落在小事上写一版。",
                        "user_premises": [message],
                        "user_actuality_quotes": [
                            "今天店里忙了一天，回家还因为谁洗碗拌了两句。"
                        ],
                        "system_creative_plan": "补出丈夫的对白和争执结果，用克制的荒诞感组织图文。",
                        "primary_value": "建立人格",
                    },
                    ensure_ascii=False,
                )
            )
        ],
    )
    request = ConversationInput(
        message=message,
        history=(
            ConversationTurn("user", "今天有点累，陪我聊两句。"),
            ConversationTurn("assistant", "那就先慢一点。"),
        ),
        brand=generation_input.brand,
        products=(),
        target="xiaohongshu_graphic",
    )

    decision = _generator().collaborate(request)

    assert decision.disposition == "ready"
    assert decision.user_premises == (message,)
    assert decision.user_actuality_quotes == (
        "今天店里忙了一天，回家还因为谁洗碗拌了两句。",
    )
    assert "补出丈夫" not in decision.system_creative_plan
    assert "只以用户本轮明确原话作为现实片段" in decision.system_creative_plan
    assert "不补人物关系" in decision.system_creative_plan
    assert "今天有点累" not in "\n".join(decision.user_premises)


def test_collaborate_discards_an_invented_actuality_quote(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    message = "帮我写条婆媳主题的小红书，别狗血。"
    _install_fake(
        monkeypatch,
        [
            _completion(
                json.dumps(
                    {
                        "kind": "ready",
                        "message": "我先写一版。",
                        "user_premises": [message],
                        "user_actuality_quotes": ["我和婆婆昨天吵了一架。"],
                        "system_creative_plan": "写一个一起做饭的具体片段并安排生活照片。",
                        "primary_value": "建立人格",
                    },
                    ensure_ascii=False,
                )
            )
        ],
    )

    decision = _generator().collaborate(
        ConversationInput(
            message=message,
            history=(),
            brand=generation_input.brand,
            products=(),
            target="xiaohongshu_graphic",
        )
    )

    assert decision.disposition == "ready"
    assert decision.user_premises == (message,)
    assert decision.user_actuality_quotes == ()
    assert "我和婆婆昨天吵了一架" not in decision.system_creative_plan
    assert "一起做饭" not in decision.system_creative_plan
    assert "现实场景" in decision.system_creative_plan


def test_collaborate_compiles_exact_premise_when_ready_payload_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    message = "今天不知道发什么，帮我做条小红书。"
    _install_fake(
        monkeypatch,
        [
            _completion(
                json.dumps(
                    {
                        "kind": "ready",
                        "message": "我先按当前账号的位置写一版。",
                        "user_premises": ["模型改写过的前提"],
                        "user_actuality_quotes": ["今天发生了一件事。"],
                    },
                    ensure_ascii=False,
                )
            )
        ],
    )

    decision = _generator().collaborate(
        ConversationInput(
            message=message,
            history=(),
            brand=generation_input.brand,
            products=(),
            target="xiaohongshu_graphic",
        )
    )

    assert decision.disposition == "ready"
    assert decision.user_premises == (message,)
    assert decision.user_actuality_quotes == ()
    assert decision.primary_product == "brand_life_narrative"
    assert decision.system_creative_plan


@pytest.mark.parametrize(
    ("model_document", "products", "expected_product"),
    [
        (
            {"kind": "chat", "message": "这个编号是想讲哪一面？"},
            (
                ProductFact(
                    "ZX-C218",
                    {"category": "双面短外套"},
                    display_name="ZX-C218 双面短外套",
                ),
            ),
            "product_truth",
        ),
        (
            {
                "kind": "question",
                "message": "你想从什么角度写？",
                "missing_fact_kind": "user_experience",
                "missing_fact_basis": "婆媳主题",
            },
            (),
            "brand_life_narrative",
        ),
    ],
)
def test_collaborate_does_not_return_system_owned_choices_to_the_user(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
    model_document: dict[str, object],
    products: tuple[ProductFact, ...],
    expected_product: str,
) -> None:
    message = (
        "ZX-C218，帮我生成一篇小红书文案。"
        if products
        else "帮我写条婆媳主题的小红书，别狗血。"
    )
    _install_fake(
        monkeypatch,
        [_completion(json.dumps(model_document, ensure_ascii=False))],
    )

    decision = _generator().collaborate(
        ConversationInput(
            message=message,
            history=(),
            brand=generation_input.brand,
            products=products,
            target="xiaohongshu_graphic",
        )
    )

    assert decision.disposition == "ready"
    assert decision.user_premises == (message,)
    assert decision.primary_product == expected_product
    assert decision.system_creative_plan


def test_collaborate_keeps_one_irreplaceable_user_fact_question(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    message = "把我去年创业最难的那个月写成视频。"
    _install_fake(
        monkeypatch,
        [
            _completion(
                json.dumps(
                    {
                        "kind": "question",
                        "message": "那个月最难的一件具体事情是什么？",
                        "missing_fact_kind": "user_experience",
                        "missing_fact_basis": "我去年创业最难的那个月",
                    },
                    ensure_ascii=False,
                )
            )
        ],
    )

    decision = _generator().collaborate(
        ConversationInput(
            message=message,
            history=(),
            brand=generation_input.brand,
            products=(),
            target="xiaohongshu_graphic",
        )
    )

    assert decision.disposition == "question"
    assert decision.message == "那个月最难的一件具体事情是什么？"


def test_collaborate_overrides_ready_for_an_unresolved_definite_user_experience(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    message = "把我去年创业最难的那个月写成视频。"
    _install_fake(
        monkeypatch,
        [
            _completion(
                json.dumps(
                    {
                        "kind": "ready",
                        "message": "我直接写一版。",
                        "user_premises": [message],
                        "user_actuality_quotes": [],
                        "system_creative_plan": "把那个月写成一段创业回顾。",
                        "primary_value": "建立人格",
                    },
                    ensure_ascii=False,
                )
            )
        ],
    )

    decision = _generator().collaborate(
        ConversationInput(
            message=message,
            history=(),
            brand=generation_input.brand,
            products=(),
            target="xiaohongshu_video",
        )
    )

    assert len(FakeClient.requests) == 1
    assert decision.disposition == "question"
    assert decision.message == "那段经历中，真正发生的一件具体事情是什么？"
    assert decision.user_premises == ()


def test_collaborate_does_not_question_a_supplied_life_fragment(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    message = "把我今天店里忙了一天、回家因为谁洗碗拌了两句写成小红书。"
    _install_fake(
        monkeypatch,
        [
            _completion(
                json.dumps(
                    {
                        "kind": "ready",
                        "message": "我直接写一版。",
                        "user_premises": [message],
                        "user_actuality_quotes": [
                            "我今天店里忙了一天、回家因为谁洗碗拌了两句"
                        ],
                        "system_creative_plan": "从疲惫落在小事上的错位选择主线。",
                        "primary_value": "建立人格",
                    },
                    ensure_ascii=False,
                )
            )
        ],
    )

    decision = _generator().collaborate(
        ConversationInput(
            message=message,
            history=(),
            brand=generation_input.brand,
            products=(),
            target="xiaohongshu_graphic",
        )
    )

    assert decision.disposition == "ready"
    assert decision.user_premises == (message,)


def test_p3_exact_actuality_and_system_plan_enter_different_fact_channels(
    generation_input: GenerationInput,
) -> None:
    actuality = "今天店里忙了一天，回家还因为谁洗碗拌了两句。"
    request = _with(
        generation_input,
        weak_seed=actuality + "帮我发条小红书。",
        primary_product="brand_life_narrative",
        user_actuality_quotes=(actuality,),
        system_creative_plan="从疲惫落在小事上的错位选择主线，用荒诞节奏组织。",
    )

    context = BoundaryContext.from_request(request)

    assert actuality in context.user_presented_actuality
    assert context.user_actuality_source == "source:user_actuality"
    assert "疲惫落在小事上的错位" in context.method_guidance
    assert "疲惫落在小事上的错位" not in context.user_presented_actuality
    assert "source:system_creative_plan" in context.source_ids

    topic_only = BoundaryContext.from_request(
        _with(
            request,
            weak_seed="帮我写条婆媳主题的小红书，别狗血。",
            user_actuality_quotes=(),
        )
    )
    assert topic_only.user_presented_actuality == ""
    assert topic_only.user_actuality_source is None


def test_p5_prompt_keeps_product_anchor_on_registered_facts(
    generation_input: GenerationInput,
) -> None:
    request = _with(generation_input, primary_product="visual_styling_story")
    prompt = DeepSeekGenerator._generation_prompt(request)

    assert "real_product_anchor 只能复述边界四已登记商品" in prompt
    assert "不得把画面命题、搭配效果、适合人群或穿着结果混入商品锚点" in prompt
    assert "visible_styling_proposition 和 visual_dependency" in prompt


def test_full_pass_compiles_visible_product_from_passed_units(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    core = _video_core()
    _install_fake(monkeypatch, [_core_response(core, tokens=10), _verdicts(core)])

    artifact = _generator().generate(generation_input)

    assert isinstance(artifact.production, VideoProductionBundle)
    spoken = "一家人的家庭感，不一定来自穿成同款。我们更愿意先尊重每个人舒服的选择，再找一个自然的呼应点。"
    assert artifact.production.spoken_lines == spoken
    assert artifact.production.subtitles == spoken
    assert artifact.production.cover_or_first_frame == "两组不同形状围住标题“不必穿成同款”。"
    assert artifact.production.visual_actions == "当前创作者自然口播，两组形状各自移动后保留呼应间距。"
    assert artifact.production.sound_and_production == "当前创作者人声，结尾留半拍安静。"
    assert artifact.production.viewing_flow == "让两组独立构成在结尾形成呼应"
    assert artifact.production.natural_duration == f"约 {DeepSeekGenerator._natural_spoken_seconds(spoken)} 秒"
    assert artifact.outline == "不必穿成同款"
    assert "标题：不必穿成同款" in artifact.body
    assert vars(artifact.semantic_contract)["choice"] == "先保留每个人舒服的选择"
    assert "当前选择：" not in artifact.body
    assert artifact.fact_repair_receipts == ()
    assert artifact.retry_count == 0
    assert len(FakeClient.requests) == 2


def test_judgement_uses_bounded_config_independent_of_writer(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    core = _video_core()
    _install_fake(monkeypatch, [_core_response(core), _verdicts(core)])

    _generator().generate(generation_input)

    writer_json = FakeClient.requests[0]["json"]
    judge_json = FakeClient.requests[1]["json"]
    assert isinstance(writer_json, dict) and isinstance(judge_json, dict)
    assert writer_json["thinking"] == {"type": "disabled"}
    assert "thinking" not in judge_json
    assert judge_json["temperature"] == 0.0
    assert judge_json["response_format"] == {"type": "json_object"}
    assert judge_json["max_tokens"] == 8192
    judge_prompt = str(judge_json["messages"])
    assert "对下面列出的每一个 id 各返回一条完整判定" in judge_prompt
    assert "identity_ok" in judge_prompt and "actuality_ok" in judge_prompt
    assert "resource_ok" in judge_prompt and "fact_ok" in judge_prompt
    assert "instruction_ok" in judge_prompt
    assert "候选自身填写的 basis、actuality 和 source_refs 只是待审声明" in judge_prompt
    assert "恰好覆盖上面列出的每个 id" in judge_prompt


@pytest.mark.parametrize(
    "mutate",
    [
        lambda verdicts: verdicts[:-1],
        lambda verdicts: [*verdicts, {**verdicts[0], "id": "unknown"}],
        lambda verdicts: [*verdicts, verdicts[0]],
        lambda verdicts: [{**verdicts[0], "identity_ok": "yes"}, *verdicts[1:]],
        lambda verdicts: [
            {key: value for key, value in verdicts[0].items() if key != "instruction_ok"},
            *verdicts[1:],
        ],
    ],
)
def test_incomplete_or_drifting_verdict_sets_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
    mutate: Any,
) -> None:
    core = _video_core()
    complete = json.loads(_verdicts(core).json()["choices"][0]["message"]["content"])
    broken = json.dumps({"verdicts": mutate(complete["verdicts"])}, ensure_ascii=False)
    _install_fake(monkeypatch, [_core_response(core), _completion(broken)])

    with pytest.raises(GenerationFailed, match="边界判定返回格式不完整"):
        _generator().generate(generation_input)


def test_legacy_sparse_violations_shape_is_no_longer_accepted(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    core = _video_core()
    _install_fake(
        monkeypatch,
        [_core_response(core), _completion(json.dumps({"violations": []}))],
    )

    with pytest.raises(GenerationFailed, match="边界判定返回格式不完整"):
        _generator().generate(generation_input)


def test_resource_verdict_repairs_an_unprovisioned_scene_before_compilation(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    unsafe = "让一家三口穿着三套衣服在门店里走动。"
    steps = [
        _step("s1", "cover", "手写标题卡：不必穿成同款。", ("c1",), resource_refs=("resource:original_composition",)),
        _step(
            "s2",
            "scene",
            unsafe,
            ("c8", "c9"),
            actor_refs=("actor:creator",),
            resource_refs=("resource:creator_expression",),
            sound_text="手机直接收录当前创作者的人声。",
        ),
    ]
    core = _video_core(steps=steps)
    repaired = _step(
        "s2",
        "scene",
        "两组不对称色块各自移动，最后保留一小段呼应的间距。",
        ("c8", "c9"),
        resource_refs=("resource:original_composition",),
        sound_text="短促节拍随色块靠近后停住。",
    )
    _install_fake(
        monkeypatch,
        [
            _core_response(core),
            _verdicts(core, {"s2": ("resource_ok",)}),
            _repairs(repaired),
            _verdicts(core),
        ],
    )

    artifact = _generator().generate(generation_input)

    assert isinstance(artifact.production, VideoProductionBundle)
    assert artifact.production.visual_actions == "两组不对称色块各自移动，最后保留一小段呼应的间距。"
    assert artifact.production.sound_and_production == "短促节拍随色块靠近后停住。"
    assert unsafe not in artifact.body
    assert {receipt.field for receipt in artifact.fact_repair_receipts} == {
        "visual_actions"
    }
    assert len(FakeClient.requests) == 4


def test_revision_verdict_repairs_unchanged_expression_and_preserves_premise(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    request = _with(
        generation_input,
        weak_seed="今天店里忙了一天，回家因为谁洗碗拌了两句。",
        primary_product="brand_life_narrative",
        user_actuality_quotes=(
            "今天店里忙了一天，回家因为谁洗碗拌了两句。",
        ),
        revision_instruction="别说教，荒诞一点，事实别变。",
        prior_saved_body=(
            "今天店里忙了一天，回家因为谁洗碗拌了两句。"
            "这种小摩擦很真实，大家要互相理解。"
        ),
    )
    core = _video_core(
        claims=[
            *cast("list[dict[str, object]]", _video_core()["claims"])[:4],
            _claim("c5", "persona_observation", "疲惫有时会落在一件小事上。"),
            _claim("c6", "audience_return", "先看见共同的疲惫，不急着判输赢。"),
            _claim("c7", "brand_account_link", "我们愿意保留这种不判输赢的观察。"),
            _claim(
                "c8",
                "spoken",
                "今天店里忙了一天，回家因为谁洗碗拌了两句。",
                "user_premise",
                "user_presented_actual",
                ("source:user_actuality",),
            ),
            _claim(
                "c9",
                "spoken",
                "这种小摩擦很真实，大家要互相理解。",
            ),
        ],
    )
    changed: dict[str, object] = {
        "claim_id": "c9",
        "text": "洗碗池像临时议会，但今晚没有议长，只有两位电量见底的代表。",
        "basis": "conditional_guidance",
        "actuality": "hypothetical",
        "source_refs": ["source:brand_baseline"],
    }
    _install_fake(
        monkeypatch,
        [
            _core_response(core),
            _verdicts(core, {"c9": ("instruction_ok",)}),
            _repairs(changed),
            _verdicts(core),
        ],
    )

    artifact = _generator().generate(request)

    assert "今天店里忙了一天，回家因为谁洗碗拌了两句。" in artifact.body
    assert "洗碗池像临时议会" in artifact.body
    assert "大家要互相理解" not in artifact.body
    assert {receipt.field for receipt in artifact.fact_repair_receipts} == {
        "spoken_lines"
    }
    repair_json = FakeClient.requests[2]["json"]
    assert isinstance(repair_json, dict)
    repair_prompt = str(repair_json["messages"])
    assert "instruction_conflict" in repair_prompt
    assert request.revision_instruction is not None
    assert request.prior_saved_body is not None
    assert request.revision_instruction in repair_prompt
    assert request.prior_saved_body in repair_prompt


def test_shared_invariant_forbids_unsourced_history_claims_in_every_prompt(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    """通用正反例（提示词层）：无来源的“曾经/反复/长期发生过”主张在写作、判定、修复三处
    都被共享不变量禁止；观点只承载当前立场、希望、主张和建议。"""
    unsourced_history = _claim(
        "c8",
        "spoken",
        "这个问题我们被问过很多次，也内部讨论过很多次。",
    )
    stance_only = _claim("c9", "spoken", "我们现在的主张是：先建立理解，再谈生意。")
    claims = [*cast("list[dict[str, object]]", _video_core()["claims"])[:7], unsourced_history, stance_only]
    core = _video_core(claims=claims)
    repaired = dict(unsourced_history)
    repaired["text"] = "如果一个品牌总被问同一个问题，答案也许就该拍成一条视频。"
    repaired["actuality"] = "hypothetical"
    _install_fake(
        monkeypatch,
        [
            _core_response(core),
            _verdicts(core, {"c8": ("actuality_ok",)}),
            _repairs(repaired),
            _verdicts(core),
        ],
    )

    artifact = _generator().generate(generation_input)

    assert "被问过很多次" not in artifact.body
    writer_prompt = str(FakeClient.requests[0]["json"]["messages"])  # type: ignore[index]
    judge_prompt = str(FakeClient.requests[1]["json"]["messages"])  # type: ignore[index]
    repair_prompt = str(FakeClient.requests[2]["json"]["messages"])  # type: ignore[index]
    for prompt in (writer_prompt, judge_prompt):
        assert "曾经、反复或长期发生过" in prompt
        assert "执行或改变" in prompt
        assert "不构成品牌或任何人已经发生过的询问、讨论、观察或经历" in prompt
    assert "共享不变量" in writer_prompt
    assert "品牌观点只能承载当前立场、希望、主张和建议" in judge_prompt
    assert "删除经历外壳" in writer_prompt and "删除经历外壳" in repair_prompt
    assert "改写为" in repair_prompt and "不得为其编造来源" in repair_prompt


def test_repair_fails_closed_when_the_same_unit_still_fails(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    core = _video_core()
    unsafe: dict[str, object] = {
        "claim_id": "c8",
        "text": "作为孩子的妈妈，我每天都这样选择。",
        "basis": "brand_viewpoint",
        "actuality": "non_event",
        "source_refs": ["source:brand_baseline"],
    }
    _install_fake(
        monkeypatch,
        [
            _core_response(core),
            _verdicts(core, {"c8": ("identity_ok",)}),
            _repairs(unsafe),
            _verdicts(core, {"c8": ("identity_ok",)}),
        ],
    )

    with pytest.raises(GenerationFailed, match="一次单元修复"):
        _generator().generate(generation_input)

    assert len(FakeClient.requests) == 4


def test_compiler_receives_the_exact_core_that_passed_the_final_review(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    """Mutation proof: a visible rewrite after final review must break this equality."""
    initial = _video_core()
    repaired_unit: dict[str, object] = {
        "claim_id": "c8",
        "text": "家庭感不必靠穿成同款证明。",
        "basis": "brand_viewpoint",
        "actuality": "non_event",
        "source_refs": ["source:brand_baseline"],
    }
    _install_fake(
        monkeypatch,
        [
            _core_response(initial),
            _verdicts(initial, {"c8": ("instruction_ok",)}),
            _repairs(repaired_unit),
            _verdicts(initial),
        ],
    )
    generator = _generator()
    reviewed_cores: list[ContentCore] = []
    compiled_cores: list[ContentCore] = []
    original_review = generator._review_core
    original_compile = generator._compile_core

    def capture_review(
        request: GenerationInput,
        context: BoundaryContext,
        core: ContentCore,
    ) -> tuple[tuple[UnitIssue, ...], dict[str, Any], int]:
        reviewed_cores.append(core)
        return original_review(request, context, core)

    def capture_compile(
        request: GenerationInput,
        core: ContentCore,
    ) -> tuple[str, ContentSemanticContract, ContentProductionBundle, str]:
        compiled_cores.append(core)
        return original_compile(request, core)

    monkeypatch.setattr(generator, "_review_core", capture_review)
    monkeypatch.setattr(generator, "_compile_core", capture_compile)

    generator.generate(generation_input)

    assert len(reviewed_cores) == 2
    assert compiled_cores == [reviewed_cores[-1]]


def test_repair_must_cover_exactly_the_violating_units(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    core = _video_core()
    _install_fake(
        monkeypatch,
        [
            _core_response(core),
            _verdicts(core, {"c8": ("actuality_ok",)}),
            _repairs(
                {
                    "claim_id": "c9",
                    "text": "换了一个没被要求修复的单元。",
                    "basis": "brand_viewpoint",
                    "actuality": "non_event",
                    "source_refs": ["source:brand_baseline"],
                }
            ),
        ],
    )

    with pytest.raises(GenerationFailed, match="修复返回格式不完整"):
        _generator().generate(generation_input)


def test_repair_accepts_an_exact_unit_mapping_without_relaxing_the_id_set(
    generation_input: GenerationInput,
) -> None:
    generator = _generator()
    context = BoundaryContext.from_request(generation_input)
    core = generator._parse_core(generation_input, context, _video_core())
    repaired = generator._merge_repaired_units(
        generation_input,
        core,
        (
            UnitIssue(
                "c8",
                "invented_actuality",
                "一家人的家庭感，不一定来自穿成同款。",
            ),
        ),
        {
            "repairs": {
                "c8": {
                    "text": "家庭感不一定来自穿成同款。",
                    "basis": "brand_viewpoint",
                    "actuality": "non_event",
                    "source_refs": ["source:brand_baseline"],
                }
            }
        },
    )

    assert repaired.claim("c8").text == "家庭感不一定来自穿成同款。"
    assert repaired.claim("c9") == core.claim("c9")


def test_closed_world_blocks_confirmed_fact_that_is_not_a_recorded_state(
    generation_input: GenerationInput,
) -> None:
    context = BoundaryContext.from_request(generation_input)
    claims = [
        _claim("c1", "title", "不必穿成同款"),
        _claim("c2", "natural_guide", "从同款进入", "user_premise", "non_event", ("source:user_request",)),
        _claim("c3", "viewing_flow", "固定机位完成口播", "conditional_guidance", "non_event"),
        _claim("c4", "release_caption", "你更在意整齐，还是自在？"),
        _claim("c5", "choice", "先保留舒服的选择", "conditional_guidance", "hypothetical"),
        _claim("c6", "boundary", "需要合照时再找呼应点", "conditional_guidance", "hypothetical"),
        _claim("c7", "next_action", "先问每个人的意愿", "conditional_guidance", "hypothetical"),
        _claim(
            "c8", "spoken", "我们见过很多家庭这样搭配。", "confirmed_fact", "hypothetical", ("source:organization",)
        ),
        _claim("c9", "spoken", "我们主张先尊重每个人的感受。"),
    ]
    core = _generator()._parse_core(generation_input, context, _video_core(claims=claims))

    issues = DeepSeekGenerator._closed_world_issues(context, core)

    assert ("c8", "invented_actuality") in {(issue.unit_id, issue.reason_code) for issue in issues}


def test_closed_world_accepts_mixed_registered_refs_with_one_carrying_source(
    generation_input: GenerationInput,
) -> None:
    """A viewpoint naming the brand cites the organization record too; that is legal."""
    context = BoundaryContext.from_request(generation_input)
    claims = [
        _claim(
            "c1",
            "title",
            "沉默也值得被尊重",
            "brand_viewpoint",
            "non_event",
            ("source:user_request", "source:brand_baseline"),
        ),
        _claim("c2", "natural_guide", "从安静浏览进入", "user_premise", "non_event", ("source:user_request",)),
        _claim("c3", "viewing_flow", "固定机位完成口播", "conditional_guidance", "non_event"),
        _claim("c4", "release_caption", "你也喜欢自己安静看看吗？"),
        _claim("c5", "choice", "先给自己留判断空间", "conditional_guidance", "hypothetical"),
        _claim("c6", "boundary", "需要帮助时再开口", "conditional_guidance", "hypothetical"),
        _claim("c7", "next_action", "下次先自己看看", "conditional_guidance", "hypothetical"),
        _claim(
            "c8",
            "spoken",
            "笛语服饰认为，家庭成员各自成立，也可以自然呼应。",
            "brand_viewpoint",
            "non_event",
            ("source:brand_baseline", "source:organization"),
        ),
        _claim(
            "c9",
            "spoken",
            "笛语服饰品牌官方账号真实存在。",
            "confirmed_fact",
            "non_event",
            ("source:organization", "source:brand_baseline"),
        ),
    ]
    core = _generator()._parse_core(generation_input, context, _video_core(claims=claims))

    assert DeepSeekGenerator._closed_world_issues(context, core) == ()


def test_closed_world_requires_one_carrying_source_for_the_basis(
    generation_input: GenerationInput,
) -> None:
    context = BoundaryContext.from_request(generation_input)
    claims = [
        *cast("list[dict[str, object]]", _video_core()["claims"])[:7],
        _claim(
            "c8",
            "spoken",
            "这是被当成已确认事实的品牌观点。",
            "confirmed_fact",
            "non_event",
            ("source:brand_baseline",),
        ),
        _claim("c9", "spoken", "我们主张先尊重每个人的感受。"),
    ]
    core = _generator()._parse_core(generation_input, context, _video_core(claims=claims))

    issues = DeepSeekGenerator._closed_world_issues(context, core)

    assert ("c8", "factual_conflict") in {(issue.unit_id, issue.reason_code) for issue in issues}


def test_closed_world_allows_faithful_user_fact_compression_for_semantic_review(
    generation_input: GenerationInput,
) -> None:
    user_fact = "今天店里忙了一天，回家还因为谁洗碗拌了两句。"
    request = _with(
        generation_input,
        primary_product="brand_life_narrative",
        user_actuality_quotes=(user_fact,),
    )
    claims = [
        *cast("list[dict[str, object]]", _video_core()["claims"])[:4],
        _claim("c5", "persona_observation", "疲惫会放大小事。"),
        _claim("c6", "audience_return", "先看见彼此都没电。"),
        _claim("c7", "brand_account_link", "我们愿意保留这种观察。"),
        _claim(
            "c8",
            "spoken",
            "今天店里忙完，回家又为洗碗拌了两句。",
            "user_premise",
            "user_presented_actual",
            ("source:user_actuality",),
        ),
        _claim("c9", "spoken", "疲惫有时会把一只碗临时升格成议题。"),
    ]
    context = BoundaryContext.from_request(request)
    core = _generator()._parse_core(request, context, _video_core(claims=claims))

    assert DeepSeekGenerator._closed_world_issues(context, core) == ()


def test_closed_world_sends_product_paraphrase_to_semantic_review_without_guessing(
    generation_input: GenerationInput,
) -> None:
    product = ProductFact(
        "ZX-C218",
        {"category": "male children short-sleeve", "colors": ["亮黄色"]},
        display_name="男童亮黄短袖",
    )
    request = _with(generation_input, products=(product,))
    claims = cast("list[dict[str, object]]", _video_core()["claims"])
    claims[7] = _claim(
        "c8",
        "spoken",
        "ZX-C218 是一件亮黄色男童短袖。",
        "confirmed_fact",
        "non_event",
        ("source:product:ZX-C218",),
    )
    context = BoundaryContext.from_request(request)
    core = _generator()._parse_core(request, context, _video_core(claims=claims))

    assert DeepSeekGenerator._closed_world_issues(context, core) == ()
    assert DeepSeekGenerator._deterministic_unit_issues(context, core) == ()


def test_deterministic_check_catches_unit_id_leak_in_visible_text(
    generation_input: GenerationInput,
) -> None:
    context = BoundaryContext.from_request(generation_input)
    steps = [
        _step("s1", "cover", "手写标题卡。", ("c1",), resource_refs=("resource:original_composition",)),
        _step(
            "s2",
            "scene",
            "当前创作者正对手机自然口播。",
            ("c8", "c9"),
            actor_refs=("actor:creator",),
            resource_refs=("resource:creator_expression",),
            sound_text="创作者口播（对应c8）。",
        ),
    ]
    core = _generator()._parse_core(generation_input, context, _video_core(steps=steps))

    issues = DeepSeekGenerator._deterministic_unit_issues(context, core)

    assert ("s2", "factual_conflict") in {(issue.unit_id, issue.reason_code) for issue in issues}
    assert "c8" in {issue.fragment for issue in issues}


@pytest.mark.parametrize(
    "shorthand",
    [
        "创作者口播：c8、c9内容",
        "口播内容：c8、c9",
        "口播：c8、c9 的内容",
        "（口播c8、c9内容）",
    ],
)
def test_pure_claim_reference_sound_text_resolves_to_spoken_lines(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
    shorthand: str,
) -> None:
    steps = [
        _step("s1", "cover", "手写标题卡：不必穿成同款。", ("c1",), resource_refs=("resource:original_composition",)),
        _step(
            "s2",
            "scene",
            "当前创作者正对手机自然口播。",
            ("c8", "c9"),
            actor_refs=("actor:creator",),
            resource_refs=("resource:creator_expression",),
            sound_text=shorthand,
        ),
    ]
    core = _video_core(steps=steps)
    _install_fake(monkeypatch, [_core_response(core), _verdicts(core)])

    artifact = _generator().generate(generation_input)

    spoken = "一家人的家庭感，不一定来自穿成同款。我们更愿意先尊重每个人舒服的选择，再找一个自然的呼应点。"
    assert isinstance(artifact.production, VideoProductionBundle)
    assert artifact.production.sound_and_production == f"创作者口播：{spoken}"
    assert "c8" not in artifact.body and "c9" not in artifact.body
    assert artifact.fact_repair_receipts == ()
    assert len(FakeClient.requests) == 2


def test_sound_reference_outside_step_claim_refs_still_fails_closed(
    generation_input: GenerationInput,
) -> None:
    context = BoundaryContext.from_request(generation_input)
    steps = [
        _step("s1", "cover", "手写标题卡。", ("c1",), resource_refs=("resource:original_composition",)),
        _step(
            "s2",
            "scene",
            "当前创作者正对手机自然口播。",
            ("c8",),
            actor_refs=("actor:creator",),
            resource_refs=("resource:creator_expression",),
            sound_text="创作者口播：c8、c9内容",
        ),
    ]
    core = _generator()._parse_core(generation_input, context, _video_core(steps=steps))

    issues = DeepSeekGenerator._deterministic_unit_issues(context, core)

    assert ("s2", "factual_conflict") in {(issue.unit_id, issue.reason_code) for issue in issues}


def test_repaired_step_with_claim_reference_shorthand_is_also_resolved(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    bad_steps = [
        _step("s1", "cover", "手写标题卡：不必穿成同款。", ("c1",), resource_refs=("resource:original_composition",)),
        _step(
            "s2",
            "scene",
            "当前创作者正对手机自然口播。",
            ("c8", "c9"),
            actor_refs=("actor:creator",),
            resource_refs=("resource:creator_expression",),
            sound_text="创作者口播（对应c8）。",
        ),
    ]
    core = _video_core(steps=bad_steps)
    repaired_step = _step(
        "s2",
        "scene",
        "当前创作者正对手机自然口播。",
        ("c8", "c9"),
        actor_refs=("actor:creator",),
        resource_refs=("resource:creator_expression",),
        sound_text="口播：c8、c9 的内容",
    )
    _install_fake(
        monkeypatch,
        [
            _core_response(core),
            _verdicts(core),
            _repairs(repaired_step),
            _verdicts(core),
        ],
    )

    artifact = _generator().generate(generation_input)

    spoken = "一家人的家庭感，不一定来自穿成同款。我们更愿意先尊重每个人舒服的选择，再找一个自然的呼应点。"
    assert isinstance(artifact.production, VideoProductionBundle)
    assert artifact.production.sound_and_production == f"创作者口播：{spoken}"
    assert "c8" not in artifact.body
    assert len(FakeClient.requests) == 4


def test_closed_world_rejects_unknown_actor_and_resource_independently(
    generation_input: GenerationInput,
) -> None:
    context = BoundaryContext.from_request(generation_input)
    steps = [
        _step("s1", "cover", "手写标题卡。", ("c1",), resource_refs=("resource:original_composition",)),
        _step(
            "s2",
            "scene",
            "妈妈牵着孩子在门店里走动。",
            ("c8",),
            actor_refs=("actor:topic_mother",),
            resource_refs=("resource:store_scene",),
            sound_text="脚步声。",
        ),
        _step(
            "s3",
            "scene",
            "当前创作者正对手机自然口播。",
            ("c9",),
            actor_refs=("actor:creator",),
            resource_refs=("resource:creator_expression",),
            sound_text="人声。",
        ),
    ]
    core = _generator()._parse_core(generation_input, context, _video_core(steps=steps))

    issues = DeepSeekGenerator._closed_world_issues(context, core)

    assert {(issue.unit_id, issue.reason_code) for issue in issues} == {
        ("s2", "untrusted_role"),
        ("s2", "unsupported_resource"),
    }


def test_structural_core_failures_get_exactly_one_regeneration(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    broken = dict(_video_core())
    del broken["scene_steps"]
    core = _video_core()
    _install_fake(
        monkeypatch,
        [
            _core_response(broken),
            _core_response(core),
            _verdicts(core),
        ],
    )

    artifact = _generator().generate(generation_input)

    assert artifact.retry_count == 1
    assert len(FakeClient.requests) == 3


@pytest.mark.parametrize(
    "mutate",
    [
        lambda core: core.update(speaker_ref="speaker:store_manager"),
        lambda core: core.update(spoken_order=["c8"]),
        lambda core: core.update(spoken_order=["c8", "c9", "c9"]),
        lambda core: core["claims"].append(_claim("c1", "spoken", "重复 id")),
        lambda core: core["claims"].pop(0),
        lambda core: core["scene_steps"].pop(0),
        lambda core: core["claims"].append(_claim("c10", "surprise_slot", "未知职责")),
    ],
)
def test_parse_core_rejects_structural_drift(
    generation_input: GenerationInput,
    mutate: Any,
) -> None:
    context = BoundaryContext.from_request(generation_input)
    core = _video_core()
    mutate(core)

    with pytest.raises((TypeError, ValueError)):
        _generator()._parse_core(generation_input, context, core)


def test_deterministic_unit_checks_keep_identifiers_and_values_exact(
    generation_input: GenerationInput,
) -> None:
    product = ProductFact(
        "ZX-C218",
        {
            "category": "double-faced short coat",
            "colors": ["炭灰面", "深绿面"],
            "sample_weight_m_grams": 960,
            "observable_features": (
                "当前样衣记录960克，对照样衣记录650克；"
                "约310克差异不能全部归因于双面结构。"
            ),
        },
    )
    request = _with(generation_input, products=(product,))
    context = BoundaryContext.from_request(request)
    good_claims = [
        _claim("c1", "title", "炭灰面"),
        _claim("c2", "natural_guide", "从当前样衣进入", "user_premise", "non_event", ("source:user_request",)),
        _claim("c3", "viewing_flow", "固定机位完成口播", "conditional_guidance", "non_event"),
        _claim("c4", "release_caption", "想看哪一面？"),
        _claim("c5", "choice", "先看两面的完整外观", "conditional_guidance", "hypothetical"),
        _claim("c6", "boundary", "如果要正式场合再定", "conditional_guidance", "hypothetical"),
        _claim("c7", "next_action", "翻面看看", "conditional_guidance", "hypothetical"),
        _claim(
            "c8",
            "spoken",
            "当前商品 ZX-C218 的样衣记录为960克，对照样衣为650克；"
            "约310克差异不能全部归因于双面结构。",
            "confirmed_fact",
            "non_event",
            ("source:product:ZX-C218",),
        ),
        _claim("c9", "spoken", "我们主张先看真实感受。"),
    ]
    bad_claims = [
        *good_claims[:7],
        _claim(
            "c8",
            "spoken",
            "当前商品 ZX-B999 的样衣记录为999克，颜色是红色；联系 test@example.com，见 source:brand_baseline。",
            "confirmed_fact",
            "non_event",
            ("source:product:ZX-C218",),
        ),
        good_claims[8],
    ]
    good_core = _generator()._parse_core(request, context, _video_core(claims=good_claims))
    bad_core = _generator()._parse_core(request, context, _video_core(claims=bad_claims))

    assert DeepSeekGenerator._deterministic_unit_issues(context, good_core) == ()
    fragments = {issue.fragment for issue in DeepSeekGenerator._deterministic_unit_issues(context, bad_core)}
    assert {"ZX-B999", "999克", "红色", "test@example.com"} <= fragments
    assert any(fragment.startswith("source:") for fragment in fragments)


def test_reviewed_product_identifier_is_not_silently_rewritten_after_review(
    generation_input: GenerationInput,
) -> None:
    product = ProductFact(
        "DIYU-CSPU-001",
        {"category": "male children short-sleeve", "colors": ["亮黄色"]},
        display_name="男童亮黄短袖（M7-2B演示商品）",
        source_kind="synthetic_business_fixture",
    )
    request = _with(generation_input, products=(product,))
    core = _video_core()
    claims = cast("list[dict[str, object]]", core["claims"])
    claims[4] = _claim(
        "c5",
        "choice",
        "先看 DIYU-CSPU-001 在当前画面里的颜色关系",
        "confirmed_fact",
        "non_event",
        ("source:product:DIYU-CSPU-001",),
    )
    steps = cast("list[dict[str, object]]", core["scene_steps"])
    steps[0] = _step(
        "s1",
        "cover",
        "手持 DIYU-CSPU-001 面向手机。",
        ("c1",),
        actor_refs=("actor:creator",),
        resource_refs=("resource:product:DIYU-CSPU-001", "resource:creator_expression"),
        production_note="画面字写 DIYU-CSPU-001。",
    )
    reviewed = _generator()._parse_core(request, BoundaryContext.from_request(request), core)
    _, _, production, body = _generator()._compile_core(request, reviewed)

    assert isinstance(production, VideoProductionBundle)
    assert "DIYU-CSPU-001" in reviewed.claim("c5").text
    assert reviewed.claim("c5").source_refs == ("source:product:DIYU-CSPU-001",)
    assert reviewed.scene_steps[0].resource_refs == (
        "resource:product:DIYU-CSPU-001",
        "resource:creator_expression",
    )
    assert "DIYU-CSPU-001" in production.cover_or_first_frame
    assert "男童亮黄短袖（M7-2B演示商品）" not in body


def test_fixed_duration_repairs_the_copy_instead_of_only_the_label(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    fixed_brand = BrandContext(
        **{
            **generation_input.brand.__dict__,
            "production_conditions": "一人一部手机，固定 8 秒。",
        }
    )
    request = _with(generation_input, brand=fixed_brand)
    long_core = _video_core(
        claims=[
            *_video_core()["claims"][:7],  # type: ignore[index]
            _claim("c8", "spoken", "这是必须真实缩短的完整口播。" * 6),
            _claim("c9", "spoken", "这一段也要跟着一起收短。" * 6),
        ]
    )
    short_c8 = "先尊重差异。"
    short_c9 = "再找呼应。"
    _install_fake(
        monkeypatch,
        [
            _core_response(long_core),
            _verdicts(long_core),
            _repairs(
                {
                    "claim_id": "c8",
                    "text": short_c8,
                    "basis": "brand_viewpoint",
                    "actuality": "non_event",
                    "source_refs": ["source:brand_baseline"],
                },
                {
                    "claim_id": "c9",
                    "text": short_c9,
                    "basis": "brand_viewpoint",
                    "actuality": "non_event",
                    "source_refs": ["source:brand_baseline"],
                },
            ),
            _verdicts(long_core),
        ],
    )

    artifact = _generator().generate(request)

    assert isinstance(artifact.production, VideoProductionBundle)
    assert artifact.production.spoken_lines == short_c8 + short_c9
    assert artifact.production.natural_duration == "8 秒"
    assert artifact.production.subtitles == short_c8 + short_c9
    assert {receipt.field for receipt in artifact.fact_repair_receipts} == {"spoken_lines"}
    repair_json = FakeClient.requests[2]["json"]
    assert isinstance(repair_json, dict)
    assert "media_contract" in str(repair_json["messages"])


def test_natural_duration_uses_at_most_four_readable_characters_per_second(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    core = _video_core()
    _install_fake(monkeypatch, [_core_response(core), _verdicts(core)])

    artifact = _generator().generate(generation_input)

    assert isinstance(artifact.production, VideoProductionBundle)
    spoken = artifact.production.spoken_lines
    seconds = int(artifact.production.natural_duration.removeprefix("约 ").removesuffix(" 秒"))
    readable = len(
        [char for char in spoken if "一" <= char <= "鿿"],
    )
    assert seconds >= (readable + 3) // 4
    assert seconds == DeepSeekGenerator._natural_spoken_seconds(spoken)


def test_graphic_core_compiles_reading_chain(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    request = _with(
        generation_input,
        target="xiaohongshu_graphic",
        media_format="graphic",
        platform_direction=direction_for("xiaohongshu_graphic"),
    )
    claims = [
        _claim("c1", "title", "不必穿成同款"),
        _claim("c2", "natural_guide", "从同款进入", "user_premise", "non_event", ("source:user_request",)),
        _claim("c3", "release_caption", "你更在意整齐，还是自在？"),
        _claim("c4", "choice", "先保留舒服的选择", "conditional_guidance", "hypothetical"),
        _claim("c5", "boundary", "需要合照时再找呼应点", "conditional_guidance", "hypothetical"),
        _claim("c6", "next_action", "先问每个人的意愿", "conditional_guidance", "hypothetical"),
        _claim("c7", "spoken", "家庭感不一定来自同款。"),
        _claim("c8", "spoken", "先尊重差异，再找自然呼应。"),
    ]
    steps = [
        _step(
            "s1",
            "cover",
            "手写标题卡特写。",
            ("c1",),
            resource_refs=("resource:original_composition",),
            production_note="自然光拍摄字卡。",
        ),
        _step(
            "s2",
            "scene",
            "创作者手持字卡示意两种选择。",
            ("c7",),
            actor_refs=("actor:creator",),
            resource_refs=("resource:original_composition",),
            production_note="同一机位连拍。",
        ),
        _step(
            "s3",
            "scene",
            "屏幕文字总结下一步。",
            ("c8",),
            resource_refs=("resource:original_composition",),
        ),
    ]
    core: dict[str, object] = {
        "speaker_ref": "speaker:brand_account",
        "claims": claims,
        "spoken_order": ["c7", "c8"],
        "scene_steps": steps,
    }
    _install_fake(monkeypatch, [_core_response(core), _verdicts(core)])

    artifact = _generator().generate(request)

    assert isinstance(artifact.production, GraphicProductionBundle)
    assert artifact.production.hero_image == "手写标题卡特写。"
    assert artifact.production.image_sequence == (
        "首图：手写标题卡特写。"
        "第2张：创作者手持字卡示意两种选择。"
        "第3张：屏幕文字总结下一步。"
    )
    assert artifact.production.full_body == "家庭感不一定来自同款。先尊重差异，再找自然呼应。"
    assert artifact.production.layout_and_production == "自然光拍摄字卡。同一机位连拍。"
    assert "首图方案" in artifact.body


def test_visual_only_story_derives_duration_from_scene_steps(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    product = ProductFact("ZX-C218", {"category": "double-faced short coat", "colors": ["炭灰面", "深绿面"]})
    request = _with(generation_input, primary_product="visual_styling_story", products=(product,))
    context = BoundaryContext.from_request(request)
    exact_anchor = next(
        statement
        for _, statement in context.product_fact_claims
        if "品类" in statement
    )
    claims = [
        _claim("c1", "title", "两面各有重音"),
        _claim("c2", "natural_guide", "从翻面进入", "user_premise", "non_event", ("source:user_request",)),
        _claim("c3", "viewing_flow", "跟随翻面动作看完", "conditional_guidance", "non_event"),
        _claim("c4", "release_caption", "你先看哪一面？"),
        _claim(
            "c5",
            "real_product_anchor",
            exact_anchor,
            "confirmed_fact",
            "non_event",
            ("source:product:ZX-C218",),
        ),
        _claim("c6", "visible_styling_proposition", "同一件外套翻面换重音", "conditional_guidance", "hypothetical"),
        _claim("c7", "visual_dependency", "翻面动作在画面中完成", "conditional_guidance", "hypothetical"),
        _claim("c8", "spoken", "无口播、无对白、无解说"),
    ]
    steps = [
        _step("s1", "cover", "外套炭灰面平铺特写。", ("c1",), resource_refs=("resource:product:ZX-C218",)),
        _step(
            "s2",
            "scene",
            "创作者把外套翻面，展示深绿面。",
            ("c6",),
            actor_refs=("actor:creator",),
            resource_refs=("resource:product:ZX-C218", "resource:creator_expression"),
            sound_text="环境底噪。",
        ),
        _step(
            "s3",
            "scene",
            "两面在画面中交替出现。",
            ("c7",),
            resource_refs=("resource:product:ZX-C218",),
        ),
    ]
    core: dict[str, object] = {
        "speaker_ref": "speaker:brand_account",
        "claims": claims,
        "spoken_order": ["c8"],
        "scene_steps": steps,
    }
    _install_fake(monkeypatch, [_core_response(core), _verdicts(core)])

    artifact = _generator().generate(request)

    assert isinstance(artifact.production, VideoProductionBundle)
    assert artifact.production.spoken_lines == "无口播、无对白、无解说"
    assert artifact.production.natural_duration == "约 6 秒"
    assert "双面短外套" in vars(artifact.semantic_contract)["real_product_anchor"]
    assert "真实商品锚点" not in artifact.body


def test_adapter_retries_provider_429_without_adding_a_boundary_retry_layer(
    monkeypatch: pytest.MonkeyPatch,
    generation_input: GenerationInput,
) -> None:
    core = _video_core()
    _install_fake(
        monkeypatch,
        [
            FakeResponse(429, {}, {"Retry-After": "0"}),
            _core_response(core, tokens=10),
            _verdicts(core),
        ],
    )
    pauses: list[float] = []
    monkeypatch.setattr(time, "sleep", pauses.append)

    artifact = _generator().generate(generation_input)

    assert artifact.model == "verified-deepseek-model"
    assert artifact.retry_count == 1
    assert artifact.provider_usage == {"total_tokens": 10}
    assert pauses == [0.0]
    assert len(FakeClient.requests) == 3
    writer_json = FakeClient.requests[1]["json"]
    assert isinstance(writer_json, dict)
    assert writer_json["temperature"] == 0.0
    assert writer_json["thinking"] == {"type": "disabled"}
    assert writer_json["response_format"] == {"type": "json_object"}


def test_nonrecoverable_provider_status_fails_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake(monkeypatch, [FakeResponse(401, {})])

    with pytest.raises(GenerationFailed, match="拒绝当前请求"):
        _generator()._request("system", "prompt", 100)

    assert len(FakeClient.requests) == 1
