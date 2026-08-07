from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from src.brain.input_role_resolver import resolve_input_roles
from src.brain.payoff_assembly import (
    assemble_task_value,
    build_payoff_request,
    product_contract_job,
)
from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.seed_demo import TENANT_ID, USER_ID
from src.shared.content_snapshot import (
    frozen_publication_contract,
    frozen_task_value_assembly,
)
from src.shared.errors import DomainError
from src.shared.narrative import user_fact_candidates
from src.shared.publication_contract import (
    AccountEditorialPermissionV3,
    BrandContextUseV3,
    PlatformDirectionV3,
    PublicationContractV2,
    PublicationContractV3,
    build_publication_contract,
    build_publication_contract_v3,
    product_brief,
    publication_contract_digest,
    publication_contract_document,
    publication_contract_from_document,
)
from src.shared.task_value_assembly import (
    assert_task_value_matches_contract,
    task_value_assembly_digest,
    task_value_assembly_document,
)
from src.shared.types import AccountExpression
from src.shared.writer_request import build_writer_request_v3

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DEEPSEEK = _REPOSITORY_ROOT / "src" / "tool" / "llm_gateway" / "deepseek.py"

# The single line the Writer consumes the payoff through.  EXE-V0 changes what the
# value is, never how the Writer receives it.
_WRITER_PAYOFF_PROMPT_LINE = "给读者的回报：{contract.audience_payoff}"

# Recorded at EXPECTED_BASE_SHA c37ae785.  The pre-V0 V2 path must keep producing it.
_HISTORICAL_V2_DIGEST = "051ebb5fc900c03e93bd2d0f9ebfd9c9b45b3835a69c1af9329cf13ccb3c8507"

_SEED = "开完一个正式会议后还要接孩子，这一身怎么穿才不用中途反复整理？"
_SEGMENTS = {
    "identity_position": "我们代表总部内容账号说话，不冒充门店店员或顾客。",
    "authority_boundary": "只讲已确认的品牌立场与商品资料；没有来源的经历不写成事实。",
    "audience_relationship": "长期服务愿意认真挑选衣服的人，保持平等、不施压的关系。",
    "content_territories": "穿衣处境、商品取舍与品牌立场三类内容可以长期经营。",
    "default_production_conditions": "一名创作者、一部手机、普通室内或门店。",
}


def _expression() -> AccountExpression:
    return AccountExpression(
        profile_id=None,
        version=1,
        is_draft=False,
        identity_position=_SEGMENTS["identity_position"],
        authority_boundary=_SEGMENTS["authority_boundary"],
        audience_relationship=_SEGMENTS["audience_relationship"],
        content_territories=_SEGMENTS["content_territories"],
        default_production_conditions=_SEGMENTS["default_production_conditions"],
    )


def _contract_v3(audience_payoff: str, *, central_job: str | None = None) -> PublicationContractV3:
    turns = ("回家才发现忘记喝水，帮我发一条。",)
    candidates = user_fact_candidates(turns)
    resolution = resolve_input_roles(
        user_turns=turns,
        candidates=candidates,
        roles={
            candidates[0].source_id: "observable_actuality",
            candidates[1].source_id: "creation_instruction",
        },
    )
    return build_publication_contract_v3(
        input_roles=resolution.spans,
        topic_origin="explicit_user",
        topic="围绕忙碌中遗漏日常步骤的张力形成一条生活观察",
        content_product="brand_life_narrative",
        central_job=central_job or product_contract_job("brand_life_narrative", "explicit_user"),
        audience_payoff=audience_payoff,
        explicit_user_controls=(candidates[1].exact_text,),
        account_editorial_permission=AccountEditorialPermissionV3(
            identity="品牌生活观察账号",
            audience="愿意认真看日常的人",
            attention_order="先看具体处境，再形成判断",
            response_posture="平等、具体、不替用户补原因",
            refusals="不新增用户身体、心理、原因或后续结果",
            allowed_stance="可以形成一般观察与低风险比喻",
            source_profile_id="profile-exev0-tests",
            source_profile_version=3,
        ),
        frozen_fact_refs=(candidates[0].source_id,),
        product_decision_basis=None,
        series_delta=None,
        platform_direction=PlatformDirectionV3(
            target="xiaohongshu_graphic",
            media_format="graphic",
            direction_version="platform-direction-v3-test",
            direction_digest="3" * 64,
        ),
        media_capability_ref="4" * 64,
        brand_context_use=BrandContextUseV3(
            available_refs=("brand-1", "method-1"),
            frozen_refs=("brand-1", "method-1"),
            consumed_refs=("method-1",),
            displayed_refs=(),
        ),
        publication_projection_id="projection-exev0-tests",
        publication_projection_version=4,
        publication_projection_digest="5" * 64,
    )


def _historical_v2_contract() -> PublicationContractV2:
    turns = ("回家才发现忘记喝水，帮我发一条。",)
    candidates = user_fact_candidates(turns)
    resolution = resolve_input_roles(
        user_turns=turns,
        candidates=candidates,
        roles={
            candidates[0].source_id: "observable_actuality",
            candidates[1].source_id: "creation_instruction",
        },
    )
    return build_publication_contract(
        primary_product="brand_life_narrative",
        topic_spans=("围绕忙碌中遗漏日常步骤的张力形成一条生活观察",),
        topic_origin="explicit_user",
        known_conditions=("普通室内",),
        frozen_fact_refs=(candidates[0].source_id,),
        intake_spans=resolution.spans,
        account_identity="品牌生活观察账号",
        account_audience="愿意认真看日常的人",
        account_attention="先看具体处境，再形成判断",
        account_response_boundary="不新增用户身体、心理、原因或后续结果",
        source_profile_id="profile-exev0-tests",
        source_profile_version=3,
        publication_projection_id="projection-exev0-tests",
        publication_projection_version=4,
        publication_projection_digest="5" * 64,
        product_value_contract_digest=None,
    )


def _assembly(content_product: str = "brand_life_narrative") -> Any:
    return assemble_task_value(
        build_payoff_request(
            content_product=content_product,
            topic_origin="explicit_user",
            account_expression=_expression(),
            product_basis=None,
            series_delta=None,
            static_payoff=product_brief(content_product, "explicit_user")[1],
        )
    )


# ---- the value the Writer receives is the value that was assembled ------------------------


def test_assembly_contract_and_writer_carry_one_identical_payoff() -> None:
    assembly = _assembly()
    contract = _contract_v3(assembly.audience_payoff)

    request = build_writer_request_v3(
        contract,
        product_decision_basis=None,
        platform_expression_responsibility="以图文页面形成完整阅读结构",
        prior_output=None,
        revision_instruction=None,
    )

    assert assembly.audience_payoff == contract.audience_payoff == request.audience_payoff


def test_the_writer_prompt_line_that_consumes_the_payoff_is_untouched() -> None:
    source = _DEEPSEEK.read_text(encoding="utf-8")

    assert _WRITER_PAYOFF_PROMPT_LINE in source
    assert source.count(_WRITER_PAYOFF_PROMPT_LINE) == 1


def test_the_contract_gate_refuses_a_payoff_that_does_not_match_the_assembly() -> None:
    assembly = _assembly()
    central_job = product_contract_job("brand_life_narrative", "explicit_user")

    with pytest.raises(DomainError, match="读者回报与冻结合同不一致"):
        assert_task_value_matches_contract(
            assembly,
            contract_audience_payoff="被悄悄换掉的回报句",
            central_job_before=central_job,
            central_job_after=central_job,
        )


def test_the_contract_gate_refuses_a_rewritten_product_contract_job() -> None:
    assembly = _assembly()

    with pytest.raises(DomainError, match="产品职责在组装前后被改写"):
        assert_task_value_matches_contract(
            assembly,
            contract_audience_payoff=assembly.audience_payoff,
            central_job_before=product_contract_job("brand_life_narrative", "explicit_user"),
            central_job_after="被组装器改写过的产品职责",
        )


# ---- history and idempotency -------------------------------------------------------------


def test_a_pre_v0_v3_snapshot_round_trips_byte_for_byte() -> None:
    contract = _contract_v3(product_brief("brand_life_narrative", "explicit_user")[1])
    document = publication_contract_document(contract)
    digest = publication_contract_digest(contract)

    persisted = json.loads(json.dumps(document, ensure_ascii=False, separators=(",", ":")))
    restored = publication_contract_from_document(persisted)

    assert publication_contract_document(restored) == document
    assert publication_contract_digest(restored) == digest


def test_the_legacy_v2_path_keeps_its_historical_digest() -> None:
    contract = _historical_v2_contract()

    assert publication_contract_digest(contract) == _HISTORICAL_V2_DIGEST
    assert publication_contract_document(contract) == publication_contract_document(
        publication_contract_from_document(publication_contract_document(contract))
    )


def test_retrying_the_same_request_reselects_the_same_template_and_digest() -> None:
    first = _assembly()
    second = _assembly()

    assert first.assembly_trace.template_id == second.assembly_trace.template_id
    assert task_value_assembly_digest(first) == task_value_assembly_digest(second)
    assert task_value_assembly_document(first) == task_value_assembly_document(second)


def test_a_pre_v0_snapshot_reports_no_assembly_and_is_never_backfilled() -> None:
    contract = _contract_v3(product_brief("brand_life_narrative", "explicit_user")[1])
    snapshot: dict[str, object] = {
        "publication_contract": publication_contract_document(contract),
        "publication_contract_digest": publication_contract_digest(contract),
    }
    before = deepcopy(snapshot)

    assert frozen_task_value_assembly(snapshot) is None
    assert snapshot == before


def test_a_tampered_assembly_snapshot_fails_closed() -> None:
    assembly = _assembly()
    snapshot: dict[str, object] = {
        "task_value_assembly": task_value_assembly_document(assembly),
        "task_value_assembly_digest": task_value_assembly_digest(assembly),
    }
    persisted = json.loads(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")))

    assert frozen_task_value_assembly(persisted) == assembly

    tampered = deepcopy(persisted)
    raw = tampered["task_value_assembly"]
    assert isinstance(raw, dict)
    raw["audience_payoff"] = "让受众拿到一句被静默替换过的、长度仍然合法的回报。"
    with pytest.raises(DomainError, match="摘要不一致"):
        frozen_task_value_assembly(tampered)

    incomplete = {"task_value_assembly": persisted["task_value_assembly"]}
    with pytest.raises(DomainError, match="价值组装不完整"):
        frozen_task_value_assembly(incomplete)


# ---- the frozen task, end to end ----------------------------------------------------------


def _content_client(app: Any) -> TestClient:
    client = TestClient(app)
    client.get("/ui/select/content")
    return client


def _rows(app_database_url: str, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    with (
        psycopg.connect(app_database_url, row_factory=dict_row) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(sql, params)
        return list(cursor.fetchall())


def _snapshot(app_database_url: str, task_id: str) -> dict[str, Any]:
    row = _rows(
        app_database_url,
        "SELECT content_context_snapshot FROM business_tasks WHERE id = %s",
        (task_id,),
    )[0]
    snapshot = row["content_context_snapshot"]
    assert isinstance(snapshot, dict)
    return snapshot


def _clear_preference(app_database_url: str, user_id: UUID) -> None:
    with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute("SELECT set_config('app.user_id', %s, true)", (str(user_id),))
        cursor.execute(
            "DELETE FROM user_creation_preferences WHERE tenant_id = %s AND user_id = %s",
            (str(TENANT_ID), str(user_id)),
        )


def test_a_new_task_freezes_its_assembly_and_a_later_profile_never_reaches_it(
    app_database_url: str,
) -> None:
    _clear_preference(app_database_url, USER_ID)
    app = create_app(Settings.model_validate({}))
    with _content_client(app) as client:
        client.post("/api/v1/content/account-expression-profile/versions", json=_SEGMENTS)
        created = client.post("/api/v1/content", json={"weak_seed": _SEED}).json()
        snapshot = _snapshot(app_database_url, created["task_id"])

        assembly = frozen_task_value_assembly(snapshot)
        contract = frozen_publication_contract(snapshot)

        assert assembly is not None
        assert isinstance(contract, PublicationContractV3)
        # The assembled value is the value the contract froze, which is the value
        # the Writer reads.  One number, three places.
        assert assembly.audience_payoff == contract.audience_payoff
        assert assembly.payoff_origin == "server_assembled"
        assert assembly.payoff_degraded is False
        assert assembly.brand_relevance_path is not None
        assert assembly.payoff_confirmation_state == "unavailable_pre_proposal"
        assert contract.central_job == product_contract_job(
            contract.content_product, contract.topic_origin
        )
        # A server-assembled payoff is no longer the static table's sentence.
        assert contract.audience_payoff != product_brief(
            contract.content_product, contract.topic_origin
        )[1]
        # Nothing from the account profile text travelled with the task.
        assembly_json = json.dumps(task_value_assembly_document(assembly), ensure_ascii=False)
        for segment in _SEGMENTS.values():
            assert segment not in assembly_json
            assert segment not in contract.audience_payoff
        assert _SEED not in assembly_json

        moved_on = dict(_SEGMENTS)
        moved_on["audience_relationship"] = "换了一版之后的受众关系说明。"
        client.post("/api/v1/content/account-expression-profile/versions", json=moved_on)

        revised = client.post(
            f"/api/v1/tasks/{created['task_id']}/revisions",
            json={"instruction": "把结尾改短一点，其他不动。"},
        ).json()
        assert revised["version"] == 2

        after = _snapshot(app_database_url, created["task_id"])
        # A revision may only add its own completion keys.  The frozen value the
        # task was produced with is re-read, never re-assembled from the newer profile.
        assert after["task_value_assembly"] == snapshot["task_value_assembly"]
        assert after["task_value_assembly_digest"] == snapshot["task_value_assembly_digest"]
        assert after["publication_contract"] == snapshot["publication_contract"]
        assert frozen_task_value_assembly(after) == assembly
        assert set(snapshot) <= set(after)
        assert moved_on["audience_relationship"] not in json.dumps(after, ensure_ascii=False)
        assert moved_on["audience_relationship"] not in revised["body"]


def test_two_different_topics_receive_two_different_payoffs(app_database_url: str) -> None:
    _clear_preference(app_database_url, USER_ID)
    app = create_app(Settings.model_validate({}))
    with _content_client(app) as client:
        client.post("/api/v1/content/account-expression-profile/versions", json=_SEGMENTS)
        first = client.post("/api/v1/content", json={"weak_seed": _SEED}).json()
        second = client.post(
            "/api/v1/content",
            json={
                "weak_seed": (
                    "上周有位客人进门第一句就是“我自己看看就好”，我们只回“需要时叫我”，"
                    "没有追问。我想让没来过的人知道，这几分钟我们会留出来。"
                )
            },
        ).json()

        payoffs = []
        products = []
        for task in (first, second):
            contract = frozen_publication_contract(_snapshot(app_database_url, task["task_id"]))
            assert isinstance(contract, PublicationContractV3)
            payoffs.append(contract.audience_payoff)
            products.append(contract.content_product)

        assert products[0] != products[1]
        assert payoffs[0] != payoffs[1]
