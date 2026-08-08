from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from src.brain.platform_directions import direction_for
from src.infrastructure.postgres_repository import PostgresContentRepository
from src.shared.errors import DomainError
from src.shared.publication_scope import (
    AUTHORIZATION_CONTRACT_VERSION,
    PUBLICATION_ITEM_SCOPE_V2_CONTRACT,
    PUBLICATION_PROJECTION_V2_CONTRACT,
    AuthorizationContractV1,
    authorization_contract_digest,
    authorization_contract_document,
    publication_projection_v2_digest,
    qualification_digest,
)
from src.shared.types import BrandContext, TrustedScope


@dataclass(frozen=True)
class GateCFixture:
    tenant_id: UUID
    other_tenant_id: UUID
    brand_id: UUID
    other_brand_id: UUID
    company_id: UUID
    region_a_id: UUID
    region_b_id: UUID
    store_a_id: UUID
    store_b_id: UUID
    user_a_id: UUID
    user_b_id: UUID
    root_store_a_id: UUID
    carrier_store_a_id: UUID
    root_region_a_id: UUID
    root_region_b_id: UUID
    root_store_b_id: UUID
    root_headquarters_id: UUID
    institutional_item_id: UUID
    task_a_id: UUID
    task_b_id: UUID
    version_a_id: UUID
    version_b_id: UUID
    observation_id: UUID


def _scope_item(
    *,
    position: int,
    text: str,
    visibility_scope: str,
    organization_ids: list[UUID],
    effective_at: datetime,
    expires_at: datetime | None = None,
    claim_key: str,
    authority_class: str = "local_formal",
    subject_type: str = "local_context",
    subject_id: str | None = None,
) -> dict[str, object]:
    return {
        "position": position,
        "publication_role": "public_brand_fact",
        "published_text": text,
        "applicability": ["local_response"],
        "source_kind": "brand_expression_baseline",
        "source_ref": f"GATEC-SOURCE-{position}",
        "source_version": "v2",
        "source_digest": sha256(text.encode()).hexdigest(),
        "visibility_scope": visibility_scope,
        "scope_organization_ids": organization_ids,
        "effective_at": effective_at,
        "expires_at": expires_at,
        "authority_class": authority_class,
        "semantic_subject_type": subject_type,
        "semantic_subject_id": subject_id,
        "claim_key": claim_key,
        "scope_contract_version": PUBLICATION_ITEM_SCOPE_V2_CONTRACT,
    }


def _insert_projection_item(
    cursor: psycopg.Cursor[tuple[object, ...]],
    *,
    tenant_id: UUID,
    brand_id: UUID,
    projection_id: UUID,
    item_id: UUID,
    item: dict[str, object],
) -> None:
    cursor.execute(
        """
        INSERT INTO brand_publication_projection_items (
            id, tenant_id, brand_id, projection_id, position,
            publication_role, published_text, applicability,
            source_kind, source_ref, source_version, source_digest,
            visibility_scope, scope_organization_ids, effective_at,
            expires_at, authority_class, semantic_subject_type,
            semantic_subject_id, claim_key, scope_contract_version
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        """,
        (
            item_id,
            tenant_id,
            brand_id,
            projection_id,
            item["position"],
            item["publication_role"],
            item["published_text"],
            item["applicability"],
            item["source_kind"],
            item["source_ref"],
            item["source_version"],
            item["source_digest"],
            item["visibility_scope"],
            item["scope_organization_ids"],
            item["effective_at"],
            item["expires_at"],
            item["authority_class"],
            item["semantic_subject_type"],
            item["semantic_subject_id"],
            item["claim_key"],
            item["scope_contract_version"],
        ),
    )


def _insert_task_version(
    cursor: psycopg.Cursor[tuple[object, ...]],
    *,
    tenant_id: UUID,
    brand_id: UUID,
    account_id: UUID,
    logical_account_id: UUID,
    user_id: UUID,
    task_id: UUID,
    version_id: UUID,
) -> None:
    run_id = uuid4()
    item_id = uuid4()
    cursor.execute(
        """
        INSERT INTO business_tasks (
            id, tenant_id, brand_id, account_id, created_by, weak_seed,
            primary_content_product, media_format, content_context_snapshot,
            logical_account_id
        ) VALUES (%s, %s, %s, %s, %s, '双用户归属夹具',
                  'local_response', 'graphic', %s, %s)
        """,
        (
            task_id,
            tenant_id,
            brand_id,
            account_id,
            user_id,
            Jsonb({"owner": str(user_id), "frozen": True}),
            logical_account_id,
        ),
    )
    cursor.execute(
        "INSERT INTO content_items (id, tenant_id, task_id, current_version) VALUES (%s, %s, %s, 1)",
        (item_id, tenant_id, task_id),
    )
    cursor.execute(
        "INSERT INTO generation_runs (id, tenant_id, task_id, model, status) VALUES (%s, %s, %s, 'stub', 'succeeded')",
        (run_id, tenant_id, task_id),
    )
    cursor.execute(
        """
        INSERT INTO content_versions (
            id, tenant_id, item_id, task_id, run_id, version_number,
            outline, body, created_by, product_contract,
            artifact_digest, version_audit_snapshot
        ) VALUES (%s, %s, %s, %s, %s, 1, '夹具标题', '夹具正文', %s,
                  '{}'::jsonb, %s, '{}'::jsonb)
        """,
        (
            version_id,
            tenant_id,
            item_id,
            task_id,
            run_id,
            user_id,
            sha256(f"{task_id}|v1".encode()).hexdigest(),
        ),
    )


@pytest.fixture(scope="module")
def gatec_fixture(migrator_database_url: str) -> GateCFixture:
    tenant_id, other_tenant_id = uuid4(), uuid4()
    brand_id, other_brand_id = uuid4(), uuid4()
    company_id, region_a_id, region_b_id, store_a_id, store_b_id = (uuid4() for _ in range(5))
    user_a_id, user_b_id = uuid4(), uuid4()
    root_store_a_id, carrier_store_a_id = uuid4(), uuid4()
    root_region_a_id, root_region_b_id, root_store_b_id, root_headquarters_id = (uuid4() for _ in range(4))
    projection_id = uuid4()
    institutional_item_id = uuid4()
    task_a_id, task_b_id, version_a_id, version_b_id = (uuid4() for _ in range(4))
    observation_id = uuid4()
    effective = datetime.now(timezone.utc) - timedelta(days=1)
    items = [
        _scope_item(
            position=1,
            text="同品牌全部逻辑账号可用",
            visibility_scope="brand_all",
            organization_ids=[],
            effective_at=effective,
            claim_key="brand_all_anchor",
            authority_class="headquarters_formal",
            subject_type="brand",
            subject_id="GATEC-BRAND",
        ),
        _scope_item(
            position=2,
            text="区域 A 的机构型天气响应",
            visibility_scope="organizations",
            organization_ids=[region_a_id],
            effective_at=effective,
            claim_key="region_a_weather",
            subject_id="REGION-A",
        ),
        _scope_item(
            position=3,
            text="门店 A 的机构型营业信息",
            visibility_scope="organizations",
            organization_ids=[store_a_id],
            effective_at=effective,
            claim_key="store_a_hours",
            subject_id="STORE-A",
        ),
        _scope_item(
            position=4,
            text="区域 B 的机构型天气响应",
            visibility_scope="organizations",
            organization_ids=[region_b_id],
            effective_at=effective,
            claim_key="region_b_weather",
            subject_id="REGION-B",
        ),
        _scope_item(
            position=5,
            text="门店 B 的机构型营业信息",
            visibility_scope="organizations",
            organization_ids=[store_b_id],
            effective_at=effective,
            claim_key="store_b_hours",
            subject_id="STORE-B",
        ),
        _scope_item(
            position=6,
            text="已经失效的活动",
            visibility_scope="brand_all",
            organization_ids=[],
            effective_at=effective - timedelta(days=10),
            expires_at=effective,
            claim_key="expired_event",
            subject_id="EXPIRED",
        ),
        _scope_item(
            position=7,
            text="尚未生效的活动",
            visibility_scope="brand_all",
            organization_ids=[],
            effective_at=effective + timedelta(days=10),
            claim_key="future_event",
            subject_id="FUTURE",
        ),
        _scope_item(
            position=8,
            text="仅根逻辑账号由公司控制时可用",
            visibility_scope="headquarters",
            organization_ids=[company_id],
            effective_at=effective,
            claim_key="headquarters_only",
            authority_class="headquarters_formal",
            subject_type="brand",
            subject_id="GATEC-BRAND",
        ),
    ]
    item_ids = [uuid4(), institutional_item_id, uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4()]
    projection_digest = publication_projection_v2_digest(items)

    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO tenants (id, name) VALUES (%s, %s)",
            (tenant_id, f"Gate C 隔离夹具-{tenant_id.hex[:8]}"),
        )
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
        organizations = (
            (company_id, "Gate C 总部", "company", None),
            (region_a_id, "Gate C 区域 A", "region", company_id),
            (region_b_id, "Gate C 区域 B", "region", company_id),
            (store_a_id, "Gate C 门店 A", "operating_unit", region_a_id),
            (store_b_id, "Gate C 门店 B", "operating_unit", region_b_id),
        )
        cursor.executemany(
            "INSERT INTO organizations "
            "(id, tenant_id, name, organization_level, parent_organization_id) "
            "VALUES (%s, %s, %s, %s, %s)",
            [(org_id, tenant_id, name, level, parent) for org_id, name, level, parent in organizations],
        )
        cursor.execute(
            "INSERT INTO brands (id, tenant_id, name, positioning, decision_order, tone) "
            "VALUES (%s, %s, 'Gate C 品牌', '作用域夹具', '结构化优先', '克制'), "
            "       (%s, %s, 'Gate C 同租户其他品牌', '隔离夹具', '不适用', '不适用')",
            (brand_id, tenant_id, other_brand_id, tenant_id),
        )
        cursor.execute(
            "INSERT INTO users (id, tenant_id, organization_id, display_name) "
            "VALUES (%s, %s, %s, 'Gate C 操作人 A'), (%s, %s, %s, 'Gate C 操作人 B')",
            (user_a_id, tenant_id, company_id, user_b_id, tenant_id, company_id),
        )
        accounts = (
            (root_store_a_id, "Gate C 门店 A 根账号", "逻辑", store_a_id, None),
            (carrier_store_a_id, "Gate C 门店 A 小红书", "小红书", None, root_store_a_id),
            (root_region_a_id, "Gate C 区域 A 账号", "小红书", region_a_id, None),
            (root_region_b_id, "Gate C 区域 B 账号", "小红书", region_b_id, None),
            (root_store_b_id, "Gate C 门店 B 账号", "小红书", store_b_id, None),
            (root_headquarters_id, "Gate C 总部账号", "小红书", company_id, None),
        )
        cursor.executemany(
            "INSERT INTO content_accounts "
            "(id, tenant_id, brand_id, name, channel, control_organization_id, "
            " carrier_of_account_id, control_organization_source) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, 'declared')",
            [
                (account_id, tenant_id, brand_id, name, channel, control_org, carrier)
                for account_id, name, channel, control_org, carrier in accounts
            ],
        )
        cursor.executemany(
            "INSERT INTO auth_grants (id, tenant_id, user_id, account_id, role_name) "
            "VALUES (%s, %s, %s, %s, 'operator')",
            [(uuid4(), tenant_id, user_id, carrier_store_a_id) for user_id in (user_a_id, user_b_id)],
        )
        cursor.execute(
            """
            INSERT INTO brand_publication_projections (
                id, tenant_id, brand_id, version_number, status, digest,
                created_by, contract_version
            ) VALUES (%s, %s, %s, 1, 'candidate', %s, %s, %s)
            """,
            (
                projection_id,
                tenant_id,
                brand_id,
                projection_digest,
                user_a_id,
                PUBLICATION_PROJECTION_V2_CONTRACT,
            ),
        )
        for item_id, item in zip(item_ids, items, strict=True):
            _insert_projection_item(
                cursor,
                tenant_id=tenant_id,
                brand_id=brand_id,
                projection_id=projection_id,
                item_id=item_id,
                item=item,
            )
        qualification_id = uuid4()
        qualification_source_digest = cast(str, items[1]["source_digest"])
        qualification_value = qualification_digest(
            {
                "path_family": "local_trust",
                "source_id": str(qualification_id),
                "source_version": "v1",
                "source_digest": qualification_source_digest,
                "organization_ref": str(region_a_id),
                "involves_person": False,
                "authorization_digest": None,
            }
        )
        cursor.execute(
            """
            INSERT INTO brand_relevance_qualifications (
                id, tenant_id, brand_id, projection_id, projection_item_id,
                path_family, organization_id, involves_person,
                qualification_version, source_digest, digest
            ) VALUES (%s, %s, %s, %s, %s, 'local_trust', %s, false,
                      'v1', %s, %s)
            """,
            (
                qualification_id,
                tenant_id,
                brand_id,
                projection_id,
                institutional_item_id,
                region_a_id,
                qualification_source_digest,
                qualification_value,
            ),
        )
        cursor.execute(
            "UPDATE brand_publication_projections SET status = 'confirmed', "
            "confirmed_by = %s, confirmed_at = transaction_timestamp() "
            "WHERE tenant_id = %s AND id = %s",
            (user_a_id, tenant_id, projection_id),
        )
        cursor.execute(
            "UPDATE brands SET current_publication_projection_id = %s WHERE tenant_id = %s AND id = %s",
            (projection_id, tenant_id, brand_id),
        )
        _insert_task_version(
            cursor,
            tenant_id=tenant_id,
            brand_id=brand_id,
            account_id=carrier_store_a_id,
            logical_account_id=root_store_a_id,
            user_id=user_a_id,
            task_id=task_a_id,
            version_id=version_a_id,
        )
        _insert_task_version(
            cursor,
            tenant_id=tenant_id,
            brand_id=brand_id,
            account_id=carrier_store_a_id,
            logical_account_id=root_store_a_id,
            user_id=user_b_id,
            task_id=task_b_id,
            version_id=version_b_id,
        )
        observation_payload = {"signal": "候选反馈，不是事实"}
        cursor.execute(
            """
            INSERT INTO brand_feedback_observations (
                id, tenant_id, brand_id, source_task_id, source_version_id,
                source_account_id, actor_id, observation_payload,
                observation_digest
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                observation_id,
                tenant_id,
                brand_id,
                task_a_id,
                version_a_id,
                carrier_store_a_id,
                user_a_id,
                Jsonb(observation_payload),
                sha256(b"gatec-observation").hexdigest(),
            ),
        )

        cursor.execute(
            "INSERT INTO tenants (id, name) VALUES (%s, %s)",
            (other_tenant_id, f"Gate C 其他租户-{other_tenant_id.hex[:8]}"),
        )
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(other_tenant_id),))
        other_org, other_brand, other_user, other_account, other_authorization = (uuid4() for _ in range(5))
        cursor.execute(
            "INSERT INTO organizations (id, tenant_id, name, organization_level) "
            "VALUES (%s, %s, '其他租户总部', 'company')",
            (other_org, other_tenant_id),
        )
        cursor.execute(
            "INSERT INTO brands (id, tenant_id, name, positioning, decision_order, tone) "
            "VALUES (%s, %s, '其他租户品牌', '隔离', '隔离', '隔离')",
            (other_brand, other_tenant_id),
        )
        cursor.execute(
            "INSERT INTO users (id, tenant_id, organization_id, display_name) VALUES (%s, %s, %s, '其他用户')",
            (other_user, other_tenant_id, other_org),
        )
        cursor.execute(
            "INSERT INTO content_accounts "
            "(id, tenant_id, brand_id, name, channel, control_organization_id, control_organization_source) "
            "VALUES (%s, %s, %s, '其他账号', '小红书', %s, 'declared')",
            (other_account, other_tenant_id, other_brand, other_org),
        )
        other_unsigned = AuthorizationContractV1(
            contract_version=AUTHORIZATION_CONTRACT_VERSION,
            authorization_id=str(other_authorization),
            authorization_version="v1",
            subject_ref="person:other",
            tenant_id=str(other_tenant_id),
            brand_id=str(other_brand),
            logical_account_id=str(other_account),
            organization_id=str(other_org),
            allowed_source_digest="e" * 64,
            allowed_usage=("organization_people",),
            single_use=True,
            effective_at=effective.isoformat(),
            expires_at=None,
            digest="",
        )
        other_contract = replace(other_unsigned, digest=authorization_contract_digest(other_unsigned))
        cursor.execute(
            """
            INSERT INTO content_authorizations (
                id, tenant_id, brand_id, logical_account_id, organization_id,
                subject_ref, authorization_version, allowed_source_digest,
                allowed_usage, single_use, effective_at, expires_at, digest,
                recorded_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, true,
                      %s, NULL, %s, %s)
            """,
            (
                other_authorization,
                other_tenant_id,
                other_brand,
                other_account,
                other_org,
                other_contract.subject_ref,
                other_contract.authorization_version,
                other_contract.allowed_source_digest,
                list(other_contract.allowed_usage),
                effective,
                other_contract.digest,
                other_user,
            ),
        )

    return GateCFixture(
        tenant_id=tenant_id,
        other_tenant_id=other_tenant_id,
        brand_id=brand_id,
        other_brand_id=other_brand_id,
        company_id=company_id,
        region_a_id=region_a_id,
        region_b_id=region_b_id,
        store_a_id=store_a_id,
        store_b_id=store_b_id,
        user_a_id=user_a_id,
        user_b_id=user_b_id,
        root_store_a_id=root_store_a_id,
        carrier_store_a_id=carrier_store_a_id,
        root_region_a_id=root_region_a_id,
        root_region_b_id=root_region_b_id,
        root_store_b_id=root_store_b_id,
        root_headquarters_id=root_headquarters_id,
        institutional_item_id=institutional_item_id,
        task_a_id=task_a_id,
        task_b_id=task_b_id,
        version_a_id=version_a_id,
        version_b_id=version_b_id,
        observation_id=observation_id,
    )


def _context() -> BrandContext:
    return BrandContext(
        brand_name="Gate C 品牌",
        positioning="作用域夹具",
        decision_order="结构化优先",
        tone="克制",
        account_name="作用域账号",
        operator_name="操作人",
        organization_name="组织",
        content_role_name="本地回应",
        content_role_boundary="只消费当前组织合法资料",
        audience_description="本地受众",
        strategy_version="v2",
        platform="小红书",
        media_format="图文",
        production_conditions="手机图文",
    )


def _selected_texts(
    repository: PostgresContentRepository,
    fixture: GateCFixture,
    *,
    account_id: UUID,
) -> tuple[str, ...]:
    context = repository.select_brand_context_for_task(
        TrustedScope(fixture.tenant_id, fixture.user_a_id, fixture.brand_id, account_id),
        _context(),
        "本地服务如何回应",
        "local_response",
        (),
    )
    packet = context.context_packet
    assert packet is not None
    return tuple(segment.exact_text for segment in packet.segments)


def test_root_logical_account_drives_headquarters_region_and_store_scope(
    app_database_url: str,
    gatec_fixture: GateCFixture,
) -> None:
    repository = PostgresContentRepository(app_database_url)
    store_a = _selected_texts(repository, gatec_fixture, account_id=gatec_fixture.carrier_store_a_id)
    region_a = _selected_texts(repository, gatec_fixture, account_id=gatec_fixture.root_region_a_id)
    region_b = _selected_texts(repository, gatec_fixture, account_id=gatec_fixture.root_region_b_id)
    store_b = _selected_texts(repository, gatec_fixture, account_id=gatec_fixture.root_store_b_id)
    headquarters = _selected_texts(repository, gatec_fixture, account_id=gatec_fixture.root_headquarters_id)

    assert "同品牌全部逻辑账号可用" in store_a
    assert "区域 A 的机构型天气响应" in store_a
    assert "门店 A 的机构型营业信息" in store_a
    assert "区域 B 的机构型天气响应" not in store_a
    assert "门店 B 的机构型营业信息" not in store_a
    assert "仅根逻辑账号由公司控制时可用" not in store_a
    assert "已经失效的活动" not in store_a
    assert "尚未生效的活动" not in store_a

    assert "区域 A 的机构型天气响应" in region_a
    assert "门店 A 的机构型营业信息" not in region_a
    assert "区域 B 的机构型天气响应" not in region_a
    assert "区域 B 的机构型天气响应" in region_b
    assert "区域 A 的机构型天气响应" not in region_b
    assert "区域 B 的机构型天气响应" in store_b
    assert "门店 B 的机构型营业信息" in store_b
    assert "区域 A 的机构型天气响应" not in store_b
    assert "仅根逻辑账号由公司控制时可用" in headquarters
    assert "区域 A 的机构型天气响应" not in headquarters


def test_institutional_local_qualification_is_read_without_person_authorization(
    app_database_url: str,
    gatec_fixture: GateCFixture,
) -> None:
    repository = PostgresContentRepository(app_database_url)
    context = repository.select_brand_context_for_task(
        TrustedScope(
            gatec_fixture.tenant_id,
            gatec_fixture.user_a_id,
            gatec_fixture.brand_id,
            gatec_fixture.root_region_a_id,
        ),
        _context(),
        "区域天气回应",
        "local_response",
        (),
    )
    assert len(context.relevance_qualifications) == 1
    qualification = context.relevance_qualifications[0]
    assert qualification.path_family == "local_trust"
    assert qualification.organization_ref == str(gatec_fixture.region_a_id)
    assert qualification.involves_person is False
    assert qualification.authorization is None


def test_tenant_rls_and_same_tenant_brand_filter_are_distinct_layers(
    app_database_url: str,
    gatec_fixture: GateCFixture,
) -> None:
    with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(gatec_fixture.tenant_id),))
        cursor.execute(
            "SELECT count(*) FROM content_authorizations WHERE tenant_id = %s",
            (gatec_fixture.other_tenant_id,),
        )
        assert cursor.fetchone() == (0,)
        cursor.execute(
            "SELECT count(*) FROM brand_feedback_observations WHERE id = %s",
            (gatec_fixture.observation_id,),
        )
        assert cursor.fetchone() == (1,)

    repository = PostgresContentRepository(app_database_url)
    with pytest.raises(DomainError):
        repository.select_brand_context_for_task(
            TrustedScope(
                gatec_fixture.tenant_id,
                gatec_fixture.user_a_id,
                gatec_fixture.other_brand_id,
                gatec_fixture.carrier_store_a_id,
            ),
            _context(),
            "跨品牌读取",
            "local_response",
            (),
        )


def test_structured_conflict_records_needs_review_and_blocks_confirmation(
    migrator_database_url: str,
    gatec_fixture: GateCFixture,
) -> None:
    conflict_brand, conflict_projection = uuid4(), uuid4()
    first_item, second_item, different_claim, nonoverlap_scope = (uuid4() for _ in range(4))
    effective = datetime.now(timezone.utc) - timedelta(hours=1)
    same_claim_a = _scope_item(
        position=1,
        text="同级正式值 A",
        visibility_scope="organizations",
        organization_ids=[gatec_fixture.region_a_id],
        effective_at=effective,
        claim_key="same_claim",
        subject_type="brand",
        subject_id="CONFLICT-BRAND",
        authority_class="local_formal",
    )
    same_claim_b = {**same_claim_a, "position": 2, "published_text": "同级正式值 B", "source_digest": "b" * 64}
    other_claim = {**same_claim_a, "position": 3, "claim_key": "different_claim"}
    other_scope = {
        **same_claim_a,
        "position": 4,
        "published_text": "区域 B 同名字段",
        "source_digest": "c" * 64,
        "scope_organization_ids": [gatec_fixture.region_b_id],
    }
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(gatec_fixture.tenant_id),))
        cursor.execute(
            "INSERT INTO brands (id, tenant_id, name, positioning, decision_order, tone) "
            "VALUES (%s, %s, %s, '冲突夹具', '结构化', '克制')",
            (conflict_brand, gatec_fixture.tenant_id, f"冲突品牌-{conflict_brand.hex[:8]}"),
        )
        cursor.execute(
            "INSERT INTO brand_publication_projections "
            "(id, tenant_id, brand_id, version_number, status, digest, created_by, contract_version) "
            "VALUES (%s, %s, %s, 1, 'candidate', %s, %s, %s)",
            (
                conflict_projection,
                gatec_fixture.tenant_id,
                conflict_brand,
                "d" * 64,
                gatec_fixture.user_a_id,
                PUBLICATION_PROJECTION_V2_CONTRACT,
            ),
        )
        for item_id, item in (
            (first_item, same_claim_a),
            (second_item, same_claim_b),
            (different_claim, other_claim),
            (nonoverlap_scope, other_scope),
        ):
            _insert_projection_item(
                cursor,
                tenant_id=gatec_fixture.tenant_id,
                brand_id=conflict_brand,
                projection_id=conflict_projection,
                item_id=item_id,
                item=item,
            )
        cursor.execute(
            "SELECT left_item_id, right_item_id, review_state "
            "FROM brand_publication_claim_conflicts "
            "WHERE tenant_id = %s AND projection_id = %s",
            (gatec_fixture.tenant_id, conflict_projection),
        )
        conflicts = cursor.fetchall()
        assert len(conflicts) == 1
        assert conflicts[0][2] == "needs_review"

    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(gatec_fixture.tenant_id),))
        with pytest.raises(psycopg.errors.RaiseException, match="claims needing review"):
            cursor.execute(
                "UPDATE brand_publication_projections SET status = 'confirmed' WHERE tenant_id = %s AND id = %s",
                (gatec_fixture.tenant_id, conflict_projection),
            )


def test_feedback_observation_is_append_only_and_cannot_become_formal_source(
    migrator_database_url: str,
    gatec_fixture: GateCFixture,
) -> None:
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(gatec_fixture.tenant_id),))
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            cursor.execute(
                "UPDATE brand_feedback_observations SET candidate_status = 'candidate' "
                "WHERE tenant_id = %s AND id = %s",
                (gatec_fixture.tenant_id, gatec_fixture.observation_id),
            )

    projection_id = uuid4()
    formalized = _scope_item(
        position=1,
        text="错误尝试将反馈升格为正式事实",
        visibility_scope="brand_all",
        organization_ids=[],
        effective_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        claim_key="forbidden_observation",
        subject_type="brand",
        subject_id="GATEC-BRAND",
        authority_class="headquarters_formal",
    )
    formalized["source_ref"] = str(gatec_fixture.observation_id)
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(gatec_fixture.tenant_id),))
        cursor.execute(
            "INSERT INTO brand_publication_projections "
            "(id, tenant_id, brand_id, version_number, status, digest, created_by, contract_version) "
            "VALUES (%s, %s, %s, 99, 'candidate', %s, %s, %s)",
            (
                projection_id,
                gatec_fixture.tenant_id,
                gatec_fixture.brand_id,
                "e" * 64,
                gatec_fixture.user_a_id,
                PUBLICATION_PROJECTION_V2_CONTRACT,
            ),
        )
        with pytest.raises(psycopg.errors.RaiseException, match="cannot be a formal projection source"):
            _insert_projection_item(
                cursor,
                tenant_id=gatec_fixture.tenant_id,
                brand_id=gatec_fixture.brand_id,
                projection_id=projection_id,
                item_id=uuid4(),
                item=formalized,
            )


def _authorization(
    fixture: GateCFixture,
    *,
    authorization_id: UUID,
    source_digest: str,
) -> AuthorizationContractV1:
    effective = datetime.now(timezone.utc) - timedelta(days=1)
    unsigned = AuthorizationContractV1(
        contract_version=AUTHORIZATION_CONTRACT_VERSION,
        authorization_id=str(authorization_id),
        authorization_version="v1",
        subject_ref=f"person:{authorization_id}",
        tenant_id=str(fixture.tenant_id),
        brand_id=str(fixture.brand_id),
        logical_account_id=str(fixture.root_store_a_id),
        organization_id=str(fixture.store_a_id),
        allowed_source_digest=source_digest,
        allowed_usage=("organization_people", "local_trust"),
        single_use=True,
        effective_at=effective.isoformat(),
        expires_at=(effective + timedelta(days=365)).isoformat(),
        digest="",
    )
    return replace(unsigned, digest=authorization_contract_digest(unsigned))


def _insert_authorization(
    cursor: psycopg.Cursor[dict[str, object]],
    fixture: GateCFixture,
    contract: AuthorizationContractV1,
) -> None:
    cursor.execute(
        """
        INSERT INTO content_authorizations (
            id, tenant_id, brand_id, logical_account_id, organization_id,
            subject_ref, authorization_version, allowed_source_digest,
            allowed_usage, single_use, effective_at, expires_at, digest,
            recorded_by
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, true,
                  %s, %s, %s, %s)
        """,
        (
            UUID(contract.authorization_id),
            fixture.tenant_id,
            fixture.brand_id,
            fixture.root_store_a_id,
            fixture.store_a_id,
            contract.subject_ref,
            contract.authorization_version,
            contract.allowed_source_digest,
            list(contract.allowed_usage),
            datetime.fromisoformat(contract.effective_at),
            datetime.fromisoformat(cast(str, contract.expires_at)),
            contract.digest,
            fixture.user_a_id,
        ),
    )


def _authorization_task(
    cursor: psycopg.Cursor[dict[str, object]],
    fixture: GateCFixture,
    *,
    user_id: UUID,
) -> tuple[UUID, UUID]:
    task_id, run_id = uuid4(), uuid4()
    cursor.execute(
        "INSERT INTO business_tasks "
        "(id, tenant_id, brand_id, account_id, created_by, weak_seed, logical_account_id) "
        "VALUES (%s, %s, %s, %s, %s, '单次授权夹具', %s)",
        (
            task_id,
            fixture.tenant_id,
            fixture.brand_id,
            fixture.carrier_store_a_id,
            user_id,
            fixture.root_store_a_id,
        ),
    )
    cursor.execute(
        "INSERT INTO generation_runs (id, tenant_id, task_id, model, status) VALUES (%s, %s, %s, 'stub', 'running')",
        (run_id, fixture.tenant_id, task_id),
    )
    return task_id, run_id


@pytest.mark.parametrize("source_digest", ("1" * 64, "2" * 64))
def test_single_use_authorization_is_consumed_once_per_task_lineage(
    app_database_url: str,
    gatec_fixture: GateCFixture,
    source_digest: str,
) -> None:
    repository = PostgresContentRepository(app_database_url)
    authorization = _authorization(gatec_fixture, authorization_id=uuid4(), source_digest=source_digest)
    scope = TrustedScope(
        gatec_fixture.tenant_id,
        gatec_fixture.user_a_id,
        gatec_fixture.brand_id,
        gatec_fixture.carrier_store_a_id,
    )
    snapshot: dict[str, object] = {
        "task_context_as_of": datetime.now(timezone.utc).isoformat(),
        "publication_contract": {
            "brand_relevance_evidence": {
                "authorization": authorization_contract_document(authorization),
            }
        },
    }
    with repository._tx(scope) as cursor:
        _insert_authorization(cursor, gatec_fixture, authorization)
        failed_task, failed_run = _authorization_task(cursor, gatec_fixture, user_id=scope.user_id)
        repository._reserve_task_authorization(
            cursor,
            scope,
            task_id=failed_task,
            run_id=failed_run,
            logical_account_id=gatec_fixture.root_store_a_id,
            task_lineage_id=failed_task,
            snapshot=snapshot,
        )
    with repository._tx(scope) as cursor:
        repository._release_task_authorization(
            cursor,
            scope,
            task_id=failed_task,
            run_id=failed_run,
        )
    with repository._tx(scope) as cursor:
        successful_task, successful_run = _authorization_task(cursor, gatec_fixture, user_id=scope.user_id)
        repository._reserve_task_authorization(
            cursor,
            scope,
            task_id=successful_task,
            run_id=successful_run,
            logical_account_id=gatec_fixture.root_store_a_id,
            task_lineage_id=successful_task,
            snapshot=snapshot,
        )
        repository._consume_task_authorization(
            cursor,
            scope,
            task_id=successful_task,
            run_id=successful_run,
        )
        revision_run = uuid4()
        cursor.execute(
            "INSERT INTO generation_runs (id, tenant_id, task_id, model, status) "
            "VALUES (%s, %s, %s, 'stub', 'running')",
            (revision_run, gatec_fixture.tenant_id, successful_task),
        )
        repository._consume_task_authorization(
            cursor,
            scope,
            task_id=successful_task,
            run_id=revision_run,
        )
        derivative_task, derivative_run = _authorization_task(
            cursor,
            gatec_fixture,
            user_id=scope.user_id,
        )
        repository._reserve_task_authorization(
            cursor,
            scope,
            task_id=derivative_task,
            run_id=derivative_run,
            logical_account_id=gatec_fixture.root_store_a_id,
            task_lineage_id=successful_task,
            snapshot=snapshot,
        )
    with pytest.raises(DomainError, match="其他任务"), repository._tx(scope) as cursor:
        other_task, other_run = _authorization_task(cursor, gatec_fixture, user_id=scope.user_id)
        repository._reserve_task_authorization(
            cursor,
            scope,
            task_id=other_task,
            run_id=other_run,
            logical_account_id=gatec_fixture.root_store_a_id,
            task_lineage_id=other_task,
            snapshot=snapshot,
        )
    with repository._tx(scope) as cursor:
        cursor.execute(
            "SELECT event_type, count(*) FROM content_authorization_events "
            "WHERE tenant_id = %s AND authorization_id = %s GROUP BY event_type",
            (gatec_fixture.tenant_id, UUID(authorization.authorization_id)),
        )
        counts = {str(row["event_type"]): int(str(row["count"])) for row in cursor.fetchall()}
    assert counts == {"reserved": 2, "released": 1, "consumed": 1}


def test_two_users_share_logical_account_but_not_each_others_tasks(
    app_database_url: str,
    gatec_fixture: GateCFixture,
) -> None:
    repository = PostgresContentRepository(app_database_url)
    scope_a = TrustedScope(
        gatec_fixture.tenant_id,
        gatec_fixture.user_a_id,
        gatec_fixture.brand_id,
        gatec_fixture.carrier_store_a_id,
    )
    scope_b = replace(scope_a, user_id=gatec_fixture.user_b_id)
    assert repository.load_content_context_snapshot(scope_a, gatec_fixture.task_a_id) == {
        "owner": str(gatec_fixture.user_a_id),
        "frozen": True,
    }
    assert repository.load_content_context_snapshot(scope_b, gatec_fixture.task_b_id) == {
        "owner": str(gatec_fixture.user_b_id),
        "frozen": True,
    }
    repository.save_version(scope_a, gatec_fixture.version_a_id)
    repository.save_version(scope_b, gatec_fixture.version_b_id)
    with pytest.raises(DomainError, match="当前作用域"):
        repository.load_content_context_snapshot(scope_a, gatec_fixture.task_b_id)
    with pytest.raises(DomainError, match="可保存"):
        repository.save_version(scope_a, gatec_fixture.version_b_id)
    with pytest.raises(DomainError, match="找不到当前租户"):
        repository.revise_task(
            scope_a,
            gatec_fixture.task_b_id,
            "跨用户修改应拒绝",
            "stub",
            (),
            _context(),
            (),
            "xiaohongshu_graphic",
            direction_for("xiaohongshu_graphic"),
            "手机图文",
        )
    with psycopg.connect(app_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(gatec_fixture.tenant_id),))
        cursor.execute(
            "SELECT created_by, logical_account_id FROM business_tasks "
            "WHERE tenant_id = %s AND id IN (%s, %s) ORDER BY created_by",
            (gatec_fixture.tenant_id, gatec_fixture.task_a_id, gatec_fixture.task_b_id),
        )
        tasks = cursor.fetchall()
        assert {row[0] for row in tasks} == {gatec_fixture.user_a_id, gatec_fixture.user_b_id}
        assert {row[1] for row in tasks} == {gatec_fixture.root_store_a_id}
        cursor.execute(
            "SELECT actor_id FROM activity_events WHERE tenant_id = %s "
            "AND event_type = 'content.saved' AND entity_id IN (%s, %s)",
            (gatec_fixture.tenant_id, gatec_fixture.version_a_id, gatec_fixture.version_b_id),
        )
        assert {row[0] for row in cursor.fetchall()} == {
            gatec_fixture.user_a_id,
            gatec_fixture.user_b_id,
        }
