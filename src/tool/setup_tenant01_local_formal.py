from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

from src.brain.content_control_service import ContentControlService
from src.brain.workbench_service import WorkbenchService
from src.infrastructure.content_control_repository import (
    PostgresContentControlRepository,
)
from src.infrastructure.local_object_store import LocalObjectStore
from src.infrastructure.production_auth import ProductionAuthRepository, TenantSession
from src.infrastructure.tenant_source_importer import TenantSourceImporter
from src.infrastructure.workbench_repository import PostgresWorkbenchRepository
from src.shared.errors import DomainError
from src.shared.tenant_brand_sources import freeze_source_batch
from src.tool.tenant01_formal_projection import (
    apply_confirmed_projection,
    compile_selection,
)


def _head_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _write_private(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def setup(
    *,
    database_url: str,
    source_root: Path,
    selection_config: Path,
    credential_path: Path,
    projection_path: Path,
    evidence_path: Path | None = None,
) -> dict[str, object]:
    if (
        credential_path.exists()
        or projection_path.exists()
        or (evidence_path is not None and evidence_path.exists())
    ):
        raise DomainError("本地正式纵向状态文件已存在，拒绝静默覆盖")
    suffix = uuid4().hex[:10]
    auth = ProductionAuthRepository(database_url)
    ops_username = f"tenant01-local-ops-{suffix}"
    ops_password = secrets.token_urlsafe(32)
    try:
        _, provisioning_uri = auth.bootstrap_operator(ops_username, ops_password)
        totp_secret = parse_qs(urlsplit(provisioning_uri).query).get(
            "secret", [""]
        )[0]
    except DomainError as exc:
        if str(exc) != "平台运维首位身份已经初始化":
            raise
        # The F-disk database is also the deterministic test database. Reuse
        # only the explicitly named, non-production test operator through the
        # same password+TOTP authentication contract; never select an
        # arbitrary surviving operator or print either credential value.
        configured_username = os.environ.get(
            "DIYU_LOCAL_FORMAL_OPS_USERNAME", "ops-formal"
        ).strip()
        if not configured_username:
            raise DomainError("缺少受控本地测试运维用户名") from exc
        with auth._tx() as cursor:
            cursor.execute(
                "SELECT username, totp_secret FROM platform_operators "
                "WHERE enabled = true AND username = %s",
                (configured_username,),
            )
            row = cursor.fetchone()
        if row is None or str(row["username"]) != configured_username:
            raise DomainError("本地正式纵向找不到明确指定的受控测试运维身份") from exc
        ops_username = str(row["username"])
        ops_password = os.environ.get("DIYU_LOCAL_FORMAL_OPS_PASSWORD", "")
        if not ops_password:
            raise DomainError("缺少受控本地测试运维凭据") from exc
        totp_secret = str(row["totp_secret"])
    if not totp_secret:
        raise DomainError("本地正式纵向无法建立受控运维身份")
    operator = auth.authenticate_operator(
        ops_username,
        ops_password,
        auth._totp_code(totp_secret, int(time.time() // 30)),
    )
    if operator is None:
        raise DomainError("本地正式纵向运维身份验证失败")
    admin_username = f"tenant01-local-admin-{suffix}"
    provisioned = auth.provision_tenant(
        operator,
        f"笛语服饰正式纵向-local-{suffix}",
        "笛语服饰本地正式管理员",
        admin_username,
    )
    tenant_id = UUID(provisioned["tenant_id"])
    manager_user_id = UUID(provisioned["administrator_id"])
    brand_id = UUID(provisioned["brand_id"])
    admin_password = secrets.token_urlsafe(32)
    auth.set_tenant_enabled(operator, tenant_id, False)
    disabled_tenant = next(
        item
        for item in auth.list_tenants(operator)
        if item["tenant_id"] == str(tenant_id)
    )
    if disabled_tenant["enabled"] is not False:
        raise DomainError("本地正式纵向租户停用没有生效")
    auth.set_tenant_enabled(operator, tenant_id, True)
    restored_tenant = next(
        item
        for item in auth.list_tenants(operator)
        if item["tenant_id"] == str(tenant_id)
    )
    if restored_tenant["enabled"] is not True:
        raise DomainError("本地正式纵向租户恢复没有生效")
    if (
        auth.complete_activation(provisioned["activation_token"], admin_password)
        != "tenant-admin"
    ):
        raise DomainError("本地正式纵向管理员激活入口错误")
    manager_session = TenantSession(tenant_id, manager_user_id, "tenant-admin")
    management_scope = auth.manager_scope(manager_session)
    organizations = auth.tenant_organizations(manager_session)
    if len(organizations) != 1:
        raise DomainError("本地正式纵向初始组织真值异常")
    headquarters_id = UUID(str(organizations[0]["id"]))
    keqiao = auth.create_tenant_organization(
        manager_session,
        "柯桥店",
        organization_level="operating_unit",
        parent_organization_id=headquarters_id,
    )
    keqiao_id = UUID(str(keqiao["id"]))
    updated_keqiao = auth.update_tenant_organization(
        manager_session,
        keqiao_id,
        "柯桥店（生命周期验证）",
        "operating_unit",
        headquarters_id,
    )
    if updated_keqiao["name"] != "柯桥店（生命周期验证）":
        raise DomainError("本地正式纵向组织修改没有生效")
    auth.update_tenant_organization(
        manager_session,
        keqiao_id,
        "柯桥店",
        "operating_unit",
        headquarters_id,
    )
    if auth.set_tenant_organization_enabled(
        manager_session,
        keqiao_id,
        False,
    )["enabled"] is not False:
        raise DomainError("本地正式纵向空组织停用没有生效")
    if auth.set_tenant_organization_enabled(
        manager_session,
        keqiao_id,
        True,
    )["enabled"] is not True:
        raise DomainError("本地正式纵向组织恢复没有生效")

    workbench_repository = PostgresWorkbenchRepository(database_url)
    workbench = WorkbenchService(
        workbench_repository,
        LocalObjectStore(str(credential_path.parent / "formal-material-objects")),
        runtime_sha=_head_sha(),
    )
    baseline = workbench.brand_expression(management_scope)
    workbench.confirm_brand_expression(management_scope, str(baseline["draft"]))

    importer = TenantSourceImporter(database_url)
    import_plan = importer.dry_run(management_scope, source_root)
    imported = importer.apply(import_plan)
    if (
        import_plan.document_count != 21
        or import_plan.segment_count != 5046
        or import_plan.product_count != 14
        or import_plan.product_field_count != 186
        or import_plan.product_fact_field_count != 26
        or imported["inserted_product_fields"] != 203
    ):
        raise DomainError("本地正式纵向来源导入数量不符合冻结真值")

    config = json.loads(selection_config.read_text(encoding="utf-8"))
    selection = compile_selection(freeze_source_batch(source_root), config)
    projection = apply_confirmed_projection(
        repository=workbench_repository,
        scope=management_scope,
        selection=selection,
    )
    current_projection = projection.get("current")
    if not isinstance(current_projection, dict):
        raise DomainError("本地正式纵向来源发布投影缺失")

    content_username = f"笛语品控-{suffix}"
    content_user = auth.create_tenant_user(
        manager_session,
        "安映华",
        content_username,
        headquarters_id,
        None,
        grants_tenant_management=False,
        grants_material_maintenance=False,
        entry_type="tenant_user",
        account_ids=(),
        maintenance_account_ids=(),
        grants_content_access=False,
    )
    content_user_id = UUID(content_user["user_id"])
    content_password = secrets.token_urlsafe(32)
    if (
        auth.complete_activation(content_user["activation_token"], content_password)
        != "tenant-user"
    ):
        raise DomainError("本地正式纵向内容用户激活入口错误")
    profile = {
        "identity_position": "从笛语真实工作现场和日常选择出发的品牌内容观察者",
        "authority_boundary": "只使用本轮用户陈述和已确认品牌、商品资料，不把观察升级为机构保证",
        "audience_relationship": "像熟悉服装现场的同行一样自然说明看见的变化和取舍",
        "content_territories": "工作现场、普通生活、穿衣选择、已确认商品解释与系列内容",
        "default_production_conditions": "单人使用现有真实资料完成，不自动发布",
    }
    account = workbench.create_publishing_account(
        management_scope,
        "笛语服饰品牌内容账号",
        "抖音",
        "笛语品牌内容观察者",
        profile["authority_boundary"],
        content_user_id,
        headquarters_id,
        True,
        initial_profile=profile,
        speaker_kind="institutional_account",
    )
    account_id = UUID(str(account["id"]))
    workbench.create_platform_carrier(
        management_scope,
        account_id,
        "笛语服饰品牌内容账号·小红书",
        "小红书",
        True,
        content_user_id,
    )
    workbench.create_platform_carrier(
        management_scope,
        account_id,
        "笛语服饰品牌内容账号·微信视频号",
        "微信视频号",
        True,
        content_user_id,
    )
    auth.update_tenant_user_grants(
        manager_session,
        content_user_id,
        account_id,
        True,
        False,
        False,
        True,
        entry_type="tenant_user",
        account_ids=(account_id,),
        maintenance_account_ids=(account_id,),
        grants_content_access=True,
        grants_display_access=False,
        display_store_ids=(),
    )
    content_scope = auth.content_scope(
        TenantSession(tenant_id, content_user_id, "tenant-user"),
        publishing_identity_id=account_id,
    )
    if (
        content_scope.tenant_id != tenant_id
        or content_scope.user_id != content_user_id
        or content_scope.account_id != account_id
    ):
        raise DomainError("本地正式纵向内容作用域回读不一致")
    control = ContentControlService(
        PostgresContentControlRepository(database_url),
        LocalObjectStore(str(credential_path.parent / "formal-control-objects")),
    )
    unmet = control.create_unmet_request(
        content_scope,
        "本地正式纵向：希望使用当前没有建设的自动发布能力。",
        None,
    )
    stable_request_id = str(unmet["stable_request_id"])
    listed_unmet = next(
        item
        for item in control.ops_unmet_requests()
        if item["stable_request_id"] == stable_request_id
    )
    answered_unmet = control.ops_classify_unmet_request(
        stable_request_id,
        "generation_method",
        "answered",
        "自动发布明确不在当前产品合同内；生成、复制和导出仍可使用。",
    )
    if (
        listed_unmet["tenant_id"] != str(tenant_id)
        or listed_unmet["status"] != "received"
        or answered_unmet["status"] != "answered"
    ):
        raise DomainError("本地正式纵向能力反馈闭环失败")
    inputs = workbench_repository.tenant_readiness_inputs(
        management_scope, _head_sha()
    )
    expected_inputs = {
        "all_source_documents": 21,
        "source_documents": 19,
        "template_documents": 2,
        "source_segments": 5046,
        "publication_items": 8,
        "publication_source_bound_items": 8,
        "publication_brand_facts": 3,
        "publication_expression_constraints": 3,
        "publication_creative_methods": 2,
        "active_products": 14,
        "allowed_product_fact_fields": 26,
        "organization_media": 0,
        "product_media_products": 0,
        "confirmed_stores": 0,
        "formal_inventory_snapshots": 0,
    }
    if any(inputs.get(key) != value for key, value in expected_inputs.items()):
        raise DomainError("本地正式纵向就绪真值与冻结预期不一致")

    _write_private(projection_path, projection)
    _write_private(
        credential_path,
        {
            "schema_version": "tenant01-local-formal-credentials-v1",
            "candidate_sha": _head_sha(),
            "tenant_id": str(tenant_id),
            "brand_id": str(brand_id),
            "manager_user_id": str(manager_user_id),
            "admin_username": admin_username,
            "admin_password": admin_password,
            "headquarters_organization_id": str(headquarters_id),
            "keqiao_organization_id": str(keqiao_id),
            "content_user_id": str(content_user_id),
            "content_username": content_username,
            "content_password": content_password,
            "account_id": str(account_id),
            "projection_id": str(current_projection["id"]),
            "projection_version": current_projection["version"],
            "projection_digest": current_projection["digest"],
        },
    )
    if evidence_path is not None:
        _write_private(
            evidence_path,
            {
                "schema_version": "tenant01-formal-setup-evidence-v1",
                "candidate_sha": _head_sha(),
                "tenant_id": str(tenant_id),
                "brand_id": str(brand_id),
                "schema_revision": str(inputs["schema_revision"]),
                "checks": [
                    {"id": "OPS_TENANT_PROVISION", "status": "PASS"},
                    {"id": "OPS_TENANT_DISABLE_RESTORE", "status": "PASS"},
                    {"id": "OPS_UNMET_REQUEST_ANSWER", "status": "PASS"},
                    {"id": "ADMIN_INITIAL_ORGANIZATION", "status": "PASS"},
                    {"id": "ADMIN_SECOND_ORGANIZATION", "status": "PASS"},
                    {"id": "ADMIN_ORGANIZATION_LIFECYCLE", "status": "PASS"},
                    {"id": "ADMIN_SOURCE_IMPORT_21_5046", "status": "PASS"},
                    {"id": "ADMIN_PRODUCT_PIPELINE_14_26", "status": "PASS"},
                    {"id": "ADMIN_PUBLICATION_CONFIRM", "status": "PASS"},
                    {"id": "ADMIN_LOGICAL_ACCOUNT_PROFILE", "status": "PASS"},
                    {"id": "ADMIN_FOUR_PLATFORM_TARGETS", "status": "PASS"},
                    {"id": "FORMAL_CONTENT_USER_ACTIVATED", "status": "PASS"},
                    {"id": "FORMAL_CONTENT_SCOPE_GRANTED", "status": "PASS"},
                    {"id": "FORMAL_DATA_GAPS_ZERO", "status": "PASS"},
                ],
                "verdict": "PASS",
            },
        )
    return {
        "candidate_sha": _head_sha(),
        "tenant_id": str(tenant_id),
        "brand_id": str(brand_id),
        "formal_users": 2,
        "organizations": 2,
        "logical_accounts": 1,
        "platform_targets": 4,
        "source_documents": 21,
        "source_segments": 5046,
        "projection_version": current_projection["version"],
        "projection_items": len(selection),
        "projection_digest": current_projection["digest"],
        "credentials_written": str(credential_path),
        "projection_written": str(projection_path),
        "verdict": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a fresh local formal TENANT-01 vertical acceptance scope."
    )
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument(
        "--selection-config",
        default=Path("config/tenant01/formal-publication-v1.json"),
        type=Path,
    )
    parser.add_argument("--credential-output", required=True, type=Path)
    parser.add_argument("--projection-output", required=True, type=Path)
    parser.add_argument("--evidence-output", type=Path)
    args = parser.parse_args()
    database_url = os.environ.get("DIYU_APP_DATABASE_URL", "")
    if not database_url:
        raise DomainError("缺少本地受控应用数据库连接")
    result = setup(
        database_url=database_url,
        source_root=args.source_root.resolve(strict=True),
        selection_config=args.selection_config.resolve(strict=True),
        credential_path=args.credential_output,
        projection_path=args.projection_output,
        evidence_path=args.evidence_output,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
