from __future__ import annotations

from uuid import UUID

import psycopg
import pytest

from src.brain.content_service import ContentService
from src.infrastructure.postgres_repository import PostgresContentRepository
from src.infrastructure.seed_demo import ACCOUNT_ID, BRAND_ID, ROLE_ID, TENANT_ID, USER_ID
from src.ports.content_generator import ContentGenerator
from src.shared.errors import DomainError
from src.shared.types import GeneratedArtifact, GenerationInput, TrustedScope
from src.tool.llm_gateway.stub import DeterministicP1Generator
from tests.conftest import BAIT_BRAND_ID, BAIT_TENANT_ID, SIBLING_BRAND_ID, SIBLING_USER_ID

_SEED = "下午开完一个挺正式的会，转身去接孩子。"
_SECOND_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000036")
_SECOND_GRANT_ID = UUID("00000000-0000-0000-0000-000000000046")
_SECOND_LINK_ID = UUID("00000000-0000-0000-0000-000000000066")
_BAIT_ORG_ID = UUID("00000000-0000-0000-0000-000000000120")
_BAIT_USER_ID = UUID("00000000-0000-0000-0000-000000000121")
_BAIT_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000122")
_CROSS_TENANT_TASK_ID = UUID("00000000-0000-0000-0000-000000000123")
_CROSS_TENANT_ITEM_ID = UUID("00000000-0000-0000-0000-000000000124")
_CROSS_TENANT_RUN_ID = UUID("00000000-0000-0000-0000-000000000125")
_CROSS_TENANT_VERSION_ID = UUID("00000000-0000-0000-0000-000000000126")
_SIBLING_TASK_ID = UUID("00000000-0000-0000-0000-000000000127")
_SIBLING_ITEM_ID = UUID("00000000-0000-0000-0000-000000000128")
_SIBLING_RUN_ID = UUID("00000000-0000-0000-0000-000000000129")
_SIBLING_VERSION_ID = UUID("00000000-0000-0000-0000-000000000130")
_CROSS_TENANT_BODY = "外租户相似历史诱饵：不得进入当前生成。"
_SIBLING_BODY = "同租户兄弟品牌相似历史诱饵：不得进入当前生成。"


class CapturingGenerator(ContentGenerator):
    def __init__(self) -> None:
        self.requests: list[GenerationInput] = []
        self._delegate = DeterministicP1Generator()

    @property
    def model_name(self) -> str:
        return self._delegate.model_name

    def generate(self, request: GenerationInput) -> GeneratedArtifact:
        self.requests.append(request)
        return self._delegate.generate(request)


def _owner_scope() -> TrustedScope:
    return TrustedScope(TENANT_ID, USER_ID, BRAND_ID, ACCOUNT_ID)


def _second_scope() -> TrustedScope:
    return TrustedScope(TENANT_ID, SIBLING_USER_ID, BRAND_ID, _SECOND_ACCOUNT_ID)


def _enable_same_brand_second_scope(migrator_database_url: str) -> None:
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            """
            INSERT INTO content_accounts (id, tenant_id, brand_id, name, channel)
            VALUES (%s, %s, %s, '折线之间第二账号', '抖音') ON CONFLICT (id) DO NOTHING
            """,
            (_SECOND_ACCOUNT_ID, TENANT_ID, BRAND_ID),
        )
        cursor.execute(
            """
            INSERT INTO auth_grants (id, tenant_id, user_id, account_id, role_name)
            VALUES (%s, %s, %s, %s, '第二账号操作权限') ON CONFLICT (id) DO NOTHING
            """,
            (_SECOND_GRANT_ID, TENANT_ID, SIBLING_USER_ID, _SECOND_ACCOUNT_ID),
        )
        cursor.execute(
            """
            INSERT INTO account_content_roles (id, tenant_id, account_id, content_role_id)
            VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING
            """,
            (_SECOND_LINK_ID, TENANT_ID, _SECOND_ACCOUNT_ID, ROLE_ID),
        )


def _insert_history(
    cursor: psycopg.Cursor[object],
    tenant_id: str,
    brand_id: UUID,
    account_id: UUID,
    user_id: UUID,
    task_id: UUID,
    item_id: UUID,
    run_id: UUID,
    version_id: UUID,
    body: str,
) -> None:
    cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
    cursor.execute(
        """
        INSERT INTO business_tasks (id, tenant_id, brand_id, account_id, created_by, weak_seed)
        VALUES (%s, %s, %s, %s, %s, '高度相似的弱种子') ON CONFLICT (id) DO NOTHING
        """,
        (task_id, tenant_id, brand_id, account_id, user_id),
    )
    cursor.execute(
        """
        INSERT INTO generation_runs (id, tenant_id, task_id, model, status)
        VALUES (%s, %s, %s, 'scope-bait', 'succeeded') ON CONFLICT (id) DO NOTHING
        """,
        (run_id, tenant_id, task_id),
    )
    cursor.execute(
        """
        INSERT INTO content_items (id, tenant_id, task_id, current_version)
        VALUES (%s, %s, %s, 1) ON CONFLICT (id) DO NOTHING
        """,
        (item_id, tenant_id, task_id),
    )
    cursor.execute(
        """
        INSERT INTO content_versions
            (id, tenant_id, item_id, task_id, run_id, version_number, outline, body, created_by)
        VALUES (%s, %s, %s, %s, %s, 1, '诱饵概要', %s, %s) ON CONFLICT (id) DO NOTHING
        """,
        (version_id, tenant_id, item_id, task_id, run_id, body, user_id),
    )


def _insert_cross_tenant_history(migrator_database_url: str) -> None:
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (BAIT_TENANT_ID,))
        cursor.execute(
            """
            INSERT INTO organizations (id, tenant_id, name)
            VALUES (%s, %s, '诱饵组织') ON CONFLICT (id) DO NOTHING
            """,
            (_BAIT_ORG_ID, BAIT_TENANT_ID),
        )
        cursor.execute(
            """
            INSERT INTO users (id, tenant_id, organization_id, display_name)
            VALUES (%s, %s, %s, '诱饵操作人') ON CONFLICT (id) DO NOTHING
            """,
            (_BAIT_USER_ID, BAIT_TENANT_ID, _BAIT_ORG_ID),
        )
        cursor.execute(
            """
            INSERT INTO content_accounts (id, tenant_id, brand_id, name, channel)
            VALUES (%s, %s, %s, '诱饵历史账号', '抖音') ON CONFLICT (id) DO NOTHING
            """,
            (_BAIT_ACCOUNT_ID, BAIT_TENANT_ID, BAIT_BRAND_ID),
        )
        _insert_history(
            cursor,
            BAIT_TENANT_ID,
            UUID(BAIT_BRAND_ID),
            _BAIT_ACCOUNT_ID,
            _BAIT_USER_ID,
            _CROSS_TENANT_TASK_ID,
            _CROSS_TENANT_ITEM_ID,
            _CROSS_TENANT_RUN_ID,
            _CROSS_TENANT_VERSION_ID,
            _CROSS_TENANT_BODY,
        )


def _insert_sibling_brand_history(migrator_database_url: str) -> None:
    with psycopg.connect(migrator_database_url) as connection, connection.cursor() as cursor:
        _insert_history(
            cursor,
            str(TENANT_ID),
            SIBLING_BRAND_ID,
            UUID("00000000-0000-0000-0000-000000000035"),
            SIBLING_USER_ID,
            _SIBLING_TASK_ID,
            _SIBLING_ITEM_ID,
            _SIBLING_RUN_ID,
            _SIBLING_VERSION_ID,
            _SIBLING_BODY,
        )


def test_history_baits_never_enter_current_generation_input(
    app_database_url: str, migrator_database_url: str
) -> None:
    _enable_same_brand_second_scope(migrator_database_url)
    _insert_cross_tenant_history(migrator_database_url)
    _insert_sibling_brand_history(migrator_database_url)
    repository = PostgresContentRepository(app_database_url)
    generator = CapturingGenerator()
    owner = ContentService(repository, generator)
    second_actor = ContentService(repository, DeterministicP1Generator())

    same_brand_other = second_actor.create_from_weak_seed(
        _second_scope(), "下午开完一个挺正式的会，转身去接孩子，外面还下着雨。"
    )
    current = owner.create_from_weak_seed(_owner_scope(), _SEED)
    continued = owner.create_from_weak_seed(_owner_scope(), "接着上一条，写成新的提醒。")
    explicit = owner.create_from_weak_seed(
        _owner_scope(), "明确复用当前上一条，换一个开头。", UUID(str(current["version_id"]))
    )
    captured_continuation = generator.requests[-2]
    captured_explicit = generator.requests[-1]
    continuation_prior = captured_continuation.prior_saved_body
    explicit_prior = captured_explicit.prior_saved_body

    assert continued["kind"] == "content"
    assert explicit["kind"] == "content"
    assert continuation_prior is not None
    assert explicit_prior is not None
    assert continuation_prior == current["body"]
    assert explicit_prior == current["body"]
    assert continuation_prior != same_brand_other["body"]
    assert _CROSS_TENANT_BODY not in continuation_prior
    assert _SIBLING_BODY not in continuation_prior
    assert captured_continuation.brand.brand_name == "折线之间"
    assert captured_continuation.brand.account_name == "折线之间品牌母账号·抖音"
    assert captured_continuation.brand.content_role_name == "总部零售/服务专家"
    assert captured_continuation.brand.audience_description.startswith("约 30—45 岁")
    assert {asset.asset_id for asset in captured_continuation.active_domain_assets} == {
        "D-DIRECT-001",
        "D-CRAFT-001",
    }
    with pytest.raises(DomainError):
        repository.fetch_version_body(_owner_scope(), _CROSS_TENANT_VERSION_ID)
    with pytest.raises(DomainError):
        repository.fetch_version_body(_owner_scope(), _SIBLING_VERSION_ID)


def test_same_brand_other_account_and_user_cannot_access_or_reuse(
    app_database_url: str, migrator_database_url: str
) -> None:
    _enable_same_brand_second_scope(migrator_database_url)
    repository = PostgresContentRepository(app_database_url)
    owner = ContentService(repository, DeterministicP1Generator())
    other = ContentService(repository, DeterministicP1Generator())
    current = owner.create_from_weak_seed(_owner_scope(), _SEED)
    version_id = UUID(str(current["version_id"]))
    task_id = UUID(str(current["task_id"]))

    with pytest.raises(DomainError):
        other.fetch_version(_second_scope(), task_id, 1)
    with pytest.raises(DomainError):
        other.revise(_second_scope(), task_id, "改写一下")
    with pytest.raises(DomainError):
        other.save_version(_second_scope(), version_id)
    with pytest.raises(DomainError):
        other.create_from_weak_seed(_second_scope(), "明确复用", version_id)
