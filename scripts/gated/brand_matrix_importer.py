"""Deterministic Gate D importer used only by the isolated rehearsal command."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.infrastructure.workbench_repository import PostgresWorkbenchRepository
from src.shared.publication_scope import publication_projection_v2_digest, qualification_digest
from src.shared.types import TenantManagementScope

GATE_D_CONTRACT_VERSION = "brand-matrix-gate-d-import-v1"
EXPECTED_MANIFEST_SHA256 = "14fed12141dc3b277c09c878a2a30ef71b445ce8ea31457c0122b403aeb48a06"
FOUNDER_ATTESTATION_REF = "ATT-GATEA-20260808-01"


def matrix_id(label: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"diyu:brand-matrix-01:{label}")


TENANT_ID = matrix_id("tenant")
BRAND_ID = matrix_id("brand")
ADMIN_USER_ID = matrix_id("user:admin")
HQ_OPERATOR_ID = matrix_id("user:hq-operator")
OPERATOR_IDS = {
    "DIYU-HQ-001": HQ_OPERATOR_ID,
    "DIYU-REGION-001": matrix_id("user:region-east"),
    "DIYU-REGION-002": matrix_id("user:region-sichuan"),
    "DIYU-STORE-001": matrix_id("user:store-hangzhou"),
    "DIYU-STORE-002": matrix_id("user:store-huzhou"),
    "DIYU-STORE-003": matrix_id("user:store-chengdu"),
}
SECOND_HANGZHOU_OPERATOR_ID = matrix_id("user:store-hangzhou-second")


_PRODUCT_NAMES = {
    "DIYU-CSPU-001": "男童明亮黄色短袖上衣",
    "DIYU-CSPU-006": "女童白色或米白色连衣裙",
    "DIYU-CSPU-008": "女童灰色松弛针织开衫",
    "DIYU-CSPU-013": "儿童灰色自然机能保暖外套",
}
_ORG_LEVELS = {
    "headquarters": "company",
    "region": "region",
    "store": "operating_unit",
}
_GLOBAL_PUBLICATION_EXTRACTS = (
    (
        "DIYU-ACCOUNT-MATRIX-001",
        "matrix-principle",
        "expression_constraint",
        "同一商品可以被不同账号使用，但必须从不同现实来源发声。",
        "expression_governance",
    ),
    (
        "DIYU-BRAND-VOICE-001",
        "voice-definition",
        "expression_constraint",
        "笛语的表达应当真实、自然、有审美判断，能够说明选择与取舍，温和但不含糊，专业但不端着。",
        "expression_governance",
    ),
    (
        "DIYU-CONTENT-GOVERNANCE-001",
        "fact-creation-boundary",
        "expression_constraint",
        "允许系统合理丰富内容，但不能把推断、创作和建议伪装成已经发生的现实事实。",
        "expression_governance",
    ),
    (
        "DIYU-ASSET-CALLING-001",
        "creative-method",
        "creative_method",
        "素材调用必须服从当前题材、账号位置、真实商品依据和实际制作条件，不为品牌关联硬改题材。",
        "expression_governance",
    ),
)

_PERSON_PUBLICATION_EXTRACTS = (
    (
        "PS-S02-05",
        "S02",
        "DIYU-STORE-001",
        "如果我们说错了，会按已确认资料更正；不得叙述为真实已发生事件。",
    ),
    (
        "PS-S04-03",
        "S04",
        "DIYU-STORE-003",
        "阿野第一次独立接待家庭，没有成交；不得把它扩写为真实顾客反馈。",
    ),
)


@dataclass(frozen=True)
class MatrixImportPlan:
    contract_version: str
    manifest_sha256: str
    batch_digest: str
    action: str
    counts: dict[str, int]
    source_sha256s: tuple[tuple[str, str], ...]

    def document(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "manifest_sha256": self.manifest_sha256,
            "batch_digest": self.batch_digest,
            "action": self.action,
            "counts": dict(sorted(self.counts.items())),
            "source_sha256s": [
                {"document_id": document_id, "sha256": digest} for document_id, digest in self.source_sha256s
            ],
        }


class BrandMatrixImporter:
    """Deterministic Gate A contract importer for one isolated or production tenant.

    The importer reads only the frozen Gate A JSON and its byte-identified source
    files.  It never scans an arbitrary directory and never promotes R-tier fields.
    """

    def __init__(
        self,
        database_url: str,
        *,
        contract_path: Path,
        manifest_path: Path,
        windows_source_root: Path,
        repository_root: Path,
    ) -> None:
        self._database_url = database_url
        self._contract_path = contract_path
        self._manifest_path = manifest_path
        self._windows_source_root = windows_source_root
        self._repository_root = repository_root

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"{path.name} must contain one object")
        return cast(dict[str, Any], value)

    def _documents(self, contract: dict[str, Any]) -> tuple[tuple[dict[str, Any], Path, bytes], ...]:
        result: list[tuple[dict[str, Any], Path, bytes]] = []
        repo_references = {
            "README.md": self._repository_root / "docs/品牌入驻候选/笛语服饰/README.md",
            "DIYU-BRAND-BASELINE-001-品牌身份与内容战略基线.md": (
                self._repository_root / "docs/品牌入驻候选/笛语服饰/DIYU-BRAND-BASELINE-001-品牌身份与内容战略基线.md"
            ),
            "DIYU-ACCOUNT-MATRIX-001-最小可用账号矩阵.md": (
                self._repository_root / "docs/品牌入驻候选/笛语服饰/DIYU-ACCOUNT-MATRIX-001-最小可用账号矩阵.md"
            ),
            "DM01-首期墙面双层挂杆候选资料.md": (
                self._repository_root / "docs/品牌入驻候选/笛语服饰/DM01-首期墙面双层挂杆候选资料.md"
            ),
        }
        for raw in contract["source_documents"]:
            record = cast(dict[str, Any], raw)
            filename = str(record["relative_filename"])
            path = (
                self._windows_source_root / filename
                if record["source_kind"] == "windows_readonly"
                else repo_references[filename]
            )
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            if digest != record["sha256"]:
                if record["source_kind"] != "repository_reference" or not record["exclusion_reason"]:
                    raise ValueError(f"source digest mismatch: {record['document_id']}")
                content = ("历史仓库引用只保留 Gate A 冻结摘要；当前文件已演进，且该对象明确不进入运行时。\n").encode()
            result.append((record, path, content))
        return tuple(result)

    def dry_run(self) -> MatrixImportPlan:
        manifest_bytes = self._manifest_path.read_bytes()
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        if manifest_sha256 != EXPECTED_MANIFEST_SHA256:
            raise ValueError("Gate A manifest digest drifted")
        contract = self._load_json(self._contract_path)
        manifest = self._load_json(self._manifest_path)
        if contract["counts"] != manifest["counts"]:
            raise ValueError("Gate A contract and manifest counts differ")
        documents = self._documents(contract)
        source_sha256s = tuple((str(record["document_id"]), str(record["sha256"])) for record, _, _ in documents)
        counts = {str(key): int(value) for key, value in cast(dict[str, Any], contract["counts"]).items()}
        plan_core = {
            "contract_version": GATE_D_CONTRACT_VERSION,
            "manifest_sha256": manifest_sha256,
            "counts": dict(sorted(counts.items())),
            "source_sha256s": source_sha256s,
            "tenant_id": str(TENANT_ID),
            "brand_id": str(BRAND_ID),
        }
        batch_digest = hashlib.sha256(
            json.dumps(plan_core, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
            cursor.execute(
                "SELECT metadata->>'batch_digest' AS digest FROM activity_events "
                "WHERE tenant_id=%s AND event_type='brand_matrix.imported' ORDER BY created_at DESC LIMIT 1",
                (TENANT_ID,),
            )
            row = cursor.fetchone()
        action = "no_op" if row is not None and row["digest"] == batch_digest else "apply"
        return MatrixImportPlan(
            contract_version=GATE_D_CONTRACT_VERSION,
            manifest_sha256=manifest_sha256,
            batch_digest=batch_digest,
            action=action,
            counts=counts,
            source_sha256s=source_sha256s,
        )

    def apply(self, plan: MatrixImportPlan) -> dict[str, object]:
        fresh = self.dry_run()
        if fresh.batch_digest != plan.batch_digest or fresh.manifest_sha256 != plan.manifest_sha256:
            raise ValueError("import inputs changed after dry-run")
        if fresh.action == "no_op":
            return {
                "status": "no_op",
                "batch_digest": plan.batch_digest,
                "inventory": self.inventory(),
                "formal_readback": self._formal_readback(),
            }
        contract = self._load_json(self._contract_path)
        documents = self._documents(contract)
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
            self._lock_fixture(cursor)
            self._archive_legacy_accounts(cursor)
            organization_ids = self._insert_organizations(cursor, contract)
            self._insert_users(cursor, organization_ids)
            account_ids = self._insert_accounts(cursor, contract, organization_ids)
            document_ids = self._insert_source_documents(cursor, documents)
            self._insert_products(cursor, contract, document_ids)
            self._insert_library(cursor, contract, organization_ids)
            self._insert_series(cursor, contract, account_ids)
            authorization_contracts = self._insert_authorizations(cursor, account_ids, organization_ids)
            self._insert_publication_projection(
                cursor,
                contract,
                document_ids,
                account_ids,
                organization_ids,
                authorization_contracts,
            )
            cursor.execute(
                "UPDATE brands SET public_name='笛语', search_aliases=ARRAY['笛语服饰'], "
                "strategy_version='v2-amd-2026-0808-01' WHERE tenant_id=%s AND id=%s",
                (TENANT_ID, BRAND_ID),
            )
            cursor.execute(
                "INSERT INTO activity_events (id,tenant_id,actor_id,event_type,entity_type,entity_id,metadata) "
                "VALUES (%s,%s,%s,'brand_matrix.imported','brand',%s,%s)",
                (
                    matrix_id("event:import"),
                    TENANT_ID,
                    ADMIN_USER_ID,
                    BRAND_ID,
                    Jsonb(
                        {
                            "batch_digest": plan.batch_digest,
                            "manifest_sha256": plan.manifest_sha256,
                            "attestation_ref": FOUNDER_ATTESTATION_REF,
                            "amendment_id": "AMD-2026-0808-01",
                        }
                    ),
                ),
            )
        return {
            "status": "applied",
            "batch_digest": plan.batch_digest,
            "inventory": self.inventory(),
            "formal_readback": self._formal_readback(),
        }

    def _formal_readback(self) -> dict[str, object]:
        repository = PostgresWorkbenchRepository(self._database_url)
        scope = TenantManagementScope(TENANT_ID, ADMIN_USER_ID, BRAND_ID)
        accounts = repository.management_accounts(scope)
        projection = repository.brand_publication_projection(scope)
        governance = repository.brand_relevance_governance(scope)
        current = projection.get("current")
        current_items = current.get("items") if isinstance(current, dict) else None
        authorizations = governance.get("authorizations")
        qualifications = governance.get("qualifications")
        platform_target_count = 0
        for item in accounts:
            raw_targets = item.get("platform_targets")
            if isinstance(raw_targets, list):
                platform_target_count += len(raw_targets)
        return {
            "logical_root_accounts": len(accounts),
            "platform_targets": platform_target_count,
            "projection_contract_version": (
                current.get("contract_version") if isinstance(current, dict) else None
            ),
            "projection_items": len(current_items) if isinstance(current_items, list) else 0,
            "authorizations": len(authorizations) if isinstance(authorizations, list) else 0,
            "qualifications": len(qualifications) if isinstance(qualifications, list) else 0,
        }

    @staticmethod
    def _lock_fixture(cursor: psycopg.Cursor[dict[str, object]]) -> None:
        cursor.execute(
            "SELECT brand.id FROM brands brand JOIN users admin ON admin.tenant_id=brand.tenant_id "
            "AND admin.id=%s AND admin.entry_kind='tenant_admin' AND admin.enabled "
            "JOIN tenant_management_grants grant_record ON grant_record.tenant_id=admin.tenant_id "
            "AND grant_record.user_id=admin.id AND grant_record.enabled "
            "WHERE brand.tenant_id=%s AND brand.id=%s FOR UPDATE OF brand",
            (ADMIN_USER_ID, TENANT_ID, BRAND_ID),
        )
        if cursor.fetchone() is None:
            raise ValueError("isolated matrix fixture is unavailable")

    @staticmethod
    def _archive_legacy_accounts(cursor: psycopg.Cursor[dict[str, object]]) -> None:
        cursor.execute(
            "UPDATE content_accounts SET enabled=false, platform_enabled=false, "
            "business_data_kind='legacy_hidden' WHERE tenant_id=%s AND brand_id=%s "
            "AND business_data_kind='synthetic_business_fixture'",
            (TENANT_ID, BRAND_ID),
        )

    @staticmethod
    def _insert_organizations(cursor: psycopg.Cursor[dict[str, object]], contract: dict[str, Any]) -> dict[str, UUID]:
        ids = {
            str(item["organization_id"]): matrix_id(f"organization:{item['organization_id']}")
            for item in contract["organizations"]
        }
        pending = list(contract["organizations"])
        while pending:
            inserted = False
            for item in tuple(pending):
                parent = item["parent_id"]
                if parent is not None and str(parent) not in ids:
                    continue
                cursor.execute(
                    "INSERT INTO organizations (id,tenant_id,name,business_data_kind,organization_level,parent_organization_id,enabled) "
                    "VALUES (%s,%s,%s,'formal_business_data',%s,%s,true)",
                    (
                        ids[str(item["organization_id"])],
                        TENANT_ID,
                        item["name"],
                        _ORG_LEVELS[str(item["organization_type"])],
                        ids[str(parent)] if parent is not None else None,
                    ),
                )
                pending.remove(item)
                inserted = True
            if not inserted:
                raise ValueError("organization hierarchy is cyclic")
        return ids

    @staticmethod
    def _insert_users(cursor: psycopg.Cursor[dict[str, object]], organization_ids: dict[str, UUID]) -> None:
        names = {
            "DIYU-HQ-001": "总部内容运营",
            "DIYU-REGION-001": "华东区域内容运营",
            "DIYU-REGION-002": "四川区域内容运营",
            "DIYU-STORE-001": "杭州西湖门店内容运营甲",
            "DIYU-STORE-002": "湖州吴兴门店内容运营",
            "DIYU-STORE-003": "成都金牛门店内容运营",
        }
        for code, user_id in OPERATOR_IDS.items():
            cursor.execute(
                "INSERT INTO users (id,tenant_id,organization_id,display_name,enabled,entry_kind,business_data_kind) "
                "VALUES (%s,%s,%s,%s,true,'tenant_user','formal_business_data')",
                (user_id, TENANT_ID, organization_ids[code], names[code]),
            )
        cursor.execute(
            "INSERT INTO users (id,tenant_id,organization_id,display_name,enabled,entry_kind,business_data_kind) "
            "VALUES (%s,%s,%s,'杭州西湖门店内容运营乙',true,'tenant_user','formal_business_data')",
            (SECOND_HANGZHOU_OPERATOR_ID, TENANT_ID, organization_ids["DIYU-STORE-001"]),
        )

    @staticmethod
    def _insert_accounts(
        cursor: psycopg.Cursor[dict[str, object]],
        contract: dict[str, Any],
        organization_ids: dict[str, UUID],
    ) -> dict[str, UUID]:
        account_ids: dict[str, UUID] = {}
        for account in contract["accounts"]:
            code = str(account["account_code"])
            account_id = matrix_id(f"account:{code}")
            account_ids[code] = account_id
            organization_code = str(account["organization_id"])
            speaker_kind = "personal_ip_account" if code in {"H02", "S04"} else "institutional_account"
            role_id = matrix_id(f"role:{code}")
            profile_id = matrix_id(f"profile:{code}:v1")
            cursor.execute(
                "INSERT INTO content_accounts "
                "(id,tenant_id,brand_id,name,channel,enabled,control_organization_id,current_expression_profile_id,"
                "control_organization_source,business_data_kind,platform_enabled) "
                "VALUES (%s,%s,%s,%s,'抖音',true,%s,NULL,'declared','formal_business_data',true)",
                (account_id, TENANT_ID, BRAND_ID, account["display_name"], organization_ids[organization_code]),
            )
            profile = cast(dict[str, Any], account["profile_segments"])
            cursor.execute(
                "INSERT INTO content_roles (id,tenant_id,brand_id,name,voice_boundary,speaker_kind) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (
                    role_id,
                    TENANT_ID,
                    BRAND_ID,
                    f"{code} {account['content_role_id']}",
                    profile["authority_boundary"]["summary"],
                    speaker_kind,
                ),
            )
            cursor.execute(
                "INSERT INTO account_content_roles (id,tenant_id,account_id,content_role_id) VALUES (%s,%s,%s,%s)",
                (matrix_id(f"account-role:{code}"), TENANT_ID, account_id, role_id),
            )
            cursor.execute(
                "INSERT INTO account_expression_profile_versions "
                "(id,tenant_id,account_id,content_role_id,version,identity_position,authority_boundary,"
                "audience_relationship,content_territories,default_production_conditions,created_by) "
                "VALUES (%s,%s,%s,%s,1,%s,%s,%s,%s,%s,%s)",
                (
                    profile_id,
                    TENANT_ID,
                    account_id,
                    role_id,
                    profile["identity_position"]["summary"],
                    profile["authority_boundary"]["summary"],
                    profile["audience_relationship"]["summary"],
                    profile["content_territory"]["summary"],
                    profile["default_production_conditions"]["summary"],
                    OPERATOR_IDS[organization_code],
                ),
            )
            cursor.execute(
                "UPDATE content_accounts SET current_expression_profile_id=%s WHERE tenant_id=%s AND id=%s",
                (profile_id, TENANT_ID, account_id),
            )
            operator_id = OPERATOR_IDS[organization_code]
            cursor.execute(
                "INSERT INTO auth_grants (id,tenant_id,user_id,account_id,role_name,enabled,can_maintain_expression_profile) "
                "VALUES (%s,%s,%s,%s,%s,true,true)",
                (matrix_id(f"grant:{code}:primary"), TENANT_ID, operator_id, account_id, f"{code} 内容操作"),
            )
            if code == "S01":
                cursor.execute(
                    "INSERT INTO auth_grants "
                    "(id,tenant_id,user_id,account_id,role_name,enabled,can_maintain_expression_profile) "
                    "VALUES (%s,%s,%s,%s,'S01 内容协作',true,false)",
                    (matrix_id("grant:S01:second"), TENANT_ID, SECOND_HANGZHOU_OPERATOR_ID, account_id),
                )
            for channel, channel_code in (("小红书", "xiaohongshu"), ("微信视频号", "wechat_video")):
                carrier_id = matrix_id(f"account:{code}:carrier:{channel_code}")
                cursor.execute(
                    "INSERT INTO content_accounts "
                    "(id,tenant_id,brand_id,name,channel,enabled,control_organization_id,"
                    "control_organization_source,carrier_of_account_id,business_data_kind,platform_enabled) "
                    "VALUES (%s,%s,%s,%s,%s,true,%s,'declared',%s,'formal_business_data',true)",
                    (
                        carrier_id,
                        TENANT_ID,
                        BRAND_ID,
                        f"{account['display_name']}·{channel}",
                        channel,
                        organization_ids[organization_code],
                        account_id,
                    ),
                )
                cursor.execute(
                    "INSERT INTO account_content_roles "
                    "(id,tenant_id,account_id,content_role_id) VALUES (%s,%s,%s,%s)",
                    (matrix_id(f"account-role:{code}:{channel_code}"), TENANT_ID, carrier_id, role_id),
                )
                cursor.execute(
                    "SELECT user_id,enabled FROM auth_grants "
                    "WHERE tenant_id=%s AND account_id=%s ORDER BY user_id",
                    (TENANT_ID, account_id),
                )
                for root_grant in cursor.fetchall():
                    user_id = UUID(str(root_grant["user_id"]))
                    cursor.execute(
                        "INSERT INTO auth_grants "
                        "(id,tenant_id,user_id,account_id,role_name,enabled,can_maintain_expression_profile) "
                        "VALUES (%s,%s,%s,%s,'平台版本载体兼容资格',%s,false)",
                        (
                            matrix_id(f"grant:{code}:{channel_code}:{user_id}"),
                            TENANT_ID,
                            user_id,
                            carrier_id,
                            bool(root_grant["enabled"]),
                        ),
                    )
        return account_ids

    def _insert_source_documents(
        self,
        cursor: psycopg.Cursor[dict[str, object]],
        documents: tuple[tuple[dict[str, Any], Path, bytes], ...],
    ) -> dict[str, tuple[UUID, UUID, str]]:
        ids: dict[str, tuple[UUID, UUID, str]] = {}
        for record, path, content_bytes in documents:
            source_id = str(record["document_id"])
            document_id = matrix_id(f"source-document:{source_id}")
            version_id = matrix_id(f"source-document:{source_id}:{record.get('version', 'v1')}")
            digest = hashlib.sha256(content_bytes).hexdigest()
            raw_digest = str(record["sha256"])
            content = content_bytes.decode("utf-8-sig")
            activation = "inactive" if record["exclusion_reason"] else "brand_user_authorized"
            status = "inactive" if record["exclusion_reason"] else "active"
            cursor.execute(
                "INSERT INTO brand_source_documents "
                "(id,tenant_id,brand_id,source_id,embedded_title,provenance_filename,source_version,original_status,"
                "activation_status,authorization_source,authorization_at,visibility_scope,status,current_version_id,created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'brand_all',%s,NULL,%s)",
                (
                    document_id,
                    TENANT_ID,
                    BRAND_ID,
                    source_id,
                    source_id,
                    path.name,
                    "v1",
                    "gatea_frozen",
                    activation,
                    FOUNDER_ATTESTATION_REF,
                    datetime(2026, 8, 8, tzinfo=timezone.utc),
                    status,
                    ADMIN_USER_ID,
                ),
            )
            cursor.execute(
                "INSERT INTO brand_source_document_versions "
                "(id,tenant_id,brand_id,document_id,source_version,embedded_title,provenance_filename,original_status,"
                "activation_status,authorization_source,authorization_at,raw_sha256,normalized_sha256,source_size,"
                "source_mtime_ns,content,created_by) "
                "VALUES (%s,%s,%s,%s,'v1',%s,%s,'gatea_frozen',%s,%s,%s,%s,%s,%s,0,%s,%s)",
                (
                    version_id,
                    TENANT_ID,
                    BRAND_ID,
                    document_id,
                    source_id,
                    path.name,
                    activation,
                    FOUNDER_ATTESTATION_REF,
                    datetime(2026, 8, 8, tzinfo=timezone.utc),
                    raw_digest,
                    digest,
                    len(content_bytes),
                    content,
                    ADMIN_USER_ID,
                ),
            )
            cursor.execute(
                "UPDATE brand_source_documents SET current_version_id=%s WHERE tenant_id=%s AND id=%s",
                (version_id, TENANT_ID, document_id),
            )
            ids[source_id] = (document_id, version_id, digest)
        for source_id, relative_path in (
            (
                "GATEA-SUPPLEMENT-REGIONAL-STORE-001",
                Path("docs/BRAND-MATRIX-01/素材草案-v0/02-组织树实例化与区域门店知识包.md"),
            ),
            (
                "GATEA-SUPPLEMENT-PERSON-SOURCES-001",
                Path("docs/BRAND-MATRIX-01/素材草案-v0/04-人物现实原句库.md"),
            ),
        ):
            path = self._repository_root / relative_path
            content_bytes = path.read_bytes()
            digest = hashlib.sha256(content_bytes).hexdigest()
            document_id = matrix_id(f"source-document:{source_id}")
            version_id = matrix_id(f"source-document:{source_id}:v1")
            cursor.execute(
                "INSERT INTO brand_source_documents "
                "(id,tenant_id,brand_id,source_id,embedded_title,provenance_filename,source_version,original_status,"
                "activation_status,authorization_source,authorization_at,visibility_scope,status,current_version_id,created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,'v1','gatea_signed_supplement','brand_user_authorized',%s,%s,"
                "'brand_all','active',NULL,%s)",
                (
                    document_id,
                    TENANT_ID,
                    BRAND_ID,
                    source_id,
                    source_id,
                    path.name,
                    FOUNDER_ATTESTATION_REF,
                    datetime(2026, 8, 8, tzinfo=timezone.utc),
                    ADMIN_USER_ID,
                ),
            )
            cursor.execute(
                "INSERT INTO brand_source_document_versions "
                "(id,tenant_id,brand_id,document_id,source_version,embedded_title,provenance_filename,original_status,"
                "activation_status,authorization_source,authorization_at,raw_sha256,normalized_sha256,source_size,"
                "source_mtime_ns,content,created_by) "
                "VALUES (%s,%s,%s,%s,'v1',%s,%s,'gatea_signed_supplement','brand_user_authorized',%s,%s,%s,%s,%s,0,%s,%s)",
                (
                    version_id,
                    TENANT_ID,
                    BRAND_ID,
                    document_id,
                    source_id,
                    path.name,
                    FOUNDER_ATTESTATION_REF,
                    datetime(2026, 8, 8, tzinfo=timezone.utc),
                    digest,
                    digest,
                    len(content_bytes),
                    content_bytes.decode("utf-8-sig"),
                    ADMIN_USER_ID,
                ),
            )
            cursor.execute(
                "UPDATE brand_source_documents SET current_version_id=%s WHERE tenant_id=%s AND id=%s",
                (version_id, TENANT_ID, document_id),
            )
            ids[source_id] = (document_id, version_id, digest)
        return ids

    @staticmethod
    def _insert_products(
        cursor: psycopg.Cursor[dict[str, object]],
        contract: dict[str, Any],
        document_ids: dict[str, tuple[UUID, UUID, str]],
    ) -> None:
        document_id, document_version_id, _ = document_ids["DIYU-CANDIDATE-PRODUCT-MASTER-001"]
        judgments_by_sku = {str(item["cspu_id"]): item for item in contract["judgments"]}
        for package in contract["deep_sku_packages"]:
            sku = str(package["cspu_id"])
            judgment = judgments_by_sku[sku]
            applicability = "；".join(str(value) for value in judgment["applicability_conditions"])
            product_id = matrix_id(f"product:{sku}")
            version_id = matrix_id(f"product:{sku}:v1")
            facts: dict[str, object] = {"entity_kind": "apparel_product"}
            fields: list[tuple[str, str]] = []
            for raw in package["product_fact_fields"]:
                key, value = str(raw).split(":", maxsplit=1)
                facts[key] = value
                fields.append((key, value))
            cursor.execute(
                "INSERT INTO brand_products "
                "(id,tenant_id,brand_id,sku,facts,display_name,source_kind,source_note,fact_version,applicability,status,"
                "updated_by,visibility_scope,current_version_id,business_data_kind,record_kind) "
                "VALUES (%s,%s,%s,%s,%s,%s,'gatea_verified_visual',%s,1,%s,'active',"
                "%s,'brand_all',NULL,'formal_business_data','confirmed_brand_product')",
                (
                    product_id,
                    TENANT_ID,
                    BRAND_ID,
                    sku,
                    Jsonb(facts),
                    _PRODUCT_NAMES[sku],
                    judgment["judgment_id"],
                    applicability,
                    ADMIN_USER_ID,
                ),
            )
            cursor.execute(
                "INSERT INTO brand_product_versions "
                "(id,tenant_id,brand_id,product_id,version_number,display_name,facts,source_kind,source_note,applicability,"
                "visibility_scope,scope_organization_ids,created_by) "
                "VALUES (%s,%s,%s,%s,1,%s,%s,'gatea_verified_visual',%s,%s,'brand_all','{}',%s)",
                (
                    version_id,
                    TENANT_ID,
                    BRAND_ID,
                    product_id,
                    _PRODUCT_NAMES[sku],
                    Jsonb(facts),
                    judgment["judgment_id"],
                    applicability,
                    ADMIN_USER_ID,
                ),
            )
            cursor.execute(
                "UPDATE brand_products SET current_version_id=%s WHERE tenant_id=%s AND id=%s",
                (version_id, TENANT_ID, product_id),
            )
            for key, value in fields:
                segment_id = matrix_id(f"product-segment:{sku}:{key}")
                exact_text = f"{key}:{value}"
                source_digest = hashlib.sha256(exact_text.encode()).hexdigest()
                cursor.execute(
                    "INSERT INTO brand_source_segments "
                    "(id,tenant_id,brand_id,document_id,document_version_id,segment_key,heading_path,source_locator,exact_text,"
                    "semantic_kind,evidence_level,applicability,visibility_scope,digest) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'candidate_product_guidance','V','P1/P2/P5','brand_all',%s)",
                    (
                        segment_id,
                        TENANT_ID,
                        BRAND_ID,
                        document_id,
                        document_version_id,
                        f"{sku}:{key}",
                        [sku],
                        package["source_anchor"],
                        exact_text,
                        source_digest,
                    ),
                )
                cursor.execute(
                    "INSERT INTO brand_product_field_evidence "
                    "(id,tenant_id,brand_id,product_id,product_version_id,field_name,exact_text,evidence_level,"
                    "source_document_id,source_segment_id,source_digest,authorization_source,allowed_in_product_fact) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,'V',%s,%s,%s,%s,true)",
                    (
                        matrix_id(f"product-evidence:{sku}:{key}"),
                        TENANT_ID,
                        BRAND_ID,
                        product_id,
                        version_id,
                        key,
                        value,
                        document_id,
                        segment_id,
                        source_digest,
                        FOUNDER_ATTESTATION_REF,
                    ),
                )

    def _regional_texts(self) -> dict[str, str]:
        path = self._repository_root / "docs/BRAND-MATRIX-01/素材草案-v0/02-组织树实例化与区域门店知识包.md"
        result: dict[str, str] = {}
        pattern = re.compile(r"^\| `([^`]+)`(?: \*\*[^*]+\*\*)? \| (.+?) \| (?:区域|门店) L[23] \|")
        for line in path.read_text(encoding="utf-8").splitlines():
            match = pattern.match(line)
            if match:
                result[match.group(1)] = re.sub(r"\*\*", "", match.group(2)).strip()
        return result

    def _insert_library(
        self,
        cursor: psycopg.Cursor[dict[str, object]],
        contract: dict[str, Any],
        organization_ids: dict[str, UUID],
    ) -> None:
        regional_texts = self._regional_texts()
        if set(regional_texts) != {str(item["entry_id"]) for item in contract["regional_store_entries"]}:
            raise ValueError("regional/store text extraction does not cover the frozen 31 entries")
        for item in contract["regional_store_entries"]:
            entry_code = str(item["entry_id"])
            entry_id = matrix_id(f"library:{entry_code}")
            version_id = matrix_id(f"library:{entry_code}:v1")
            organization_id = organization_ids[str(item["organization_id"])]
            status = "retired" if str(item["status"]).startswith("expired_") else "active"
            content = regional_texts[entry_code]
            cursor.execute(
                "INSERT INTO brand_library_entries "
                "(id,tenant_id,brand_id,category,title,source_note,content,version,status,visibility_scope,updated_by,"
                "current_version_id,business_data_kind) "
                "VALUES (%s,%s,%s,'local_context',%s,%s,%s,'v1',%s,'organizations',%s,NULL,'formal_business_data')",
                (
                    entry_id,
                    TENANT_ID,
                    BRAND_ID,
                    entry_code,
                    item["source_anchor"],
                    content,
                    status,
                    ADMIN_USER_ID,
                ),
            )
            cursor.execute(
                "INSERT INTO brand_library_entry_versions "
                "(id,tenant_id,brand_id,entry_id,version_number,version_label,category,title,source_note,content,"
                "visibility_scope,scope_organization_ids,created_by) "
                "VALUES (%s,%s,%s,%s,1,'v1','local_context',%s,%s,%s,'organizations',%s,%s)",
                (
                    version_id,
                    TENANT_ID,
                    BRAND_ID,
                    entry_id,
                    entry_code,
                    item["source_anchor"],
                    content,
                    [organization_id],
                    ADMIN_USER_ID,
                ),
            )
            cursor.execute(
                "UPDATE brand_library_entries SET current_version_id=%s WHERE tenant_id=%s AND id=%s",
                (version_id, TENANT_ID, entry_id),
            )
            cursor.execute(
                "INSERT INTO brand_library_entry_organizations (id,tenant_id,entry_id,organization_id) "
                "VALUES (%s,%s,%s,%s)",
                (matrix_id(f"library-scope:{entry_code}"), TENANT_ID, entry_id, organization_id),
            )
        for judgment in contract["judgments"]:
            code = str(judgment["judgment_id"])
            content = json.dumps(
                {
                    "cspu_id": judgment["cspu_id"],
                    "judgment_owner": judgment["judgment_owner"],
                    "applicability_conditions": judgment["applicability_conditions"],
                    "evidence_refs": judgment["evidence_refs"],
                    "approved_by": "founder",
                    "attestation_ref": FOUNDER_ATTESTATION_REF,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            entry_id = matrix_id(f"library:{code}")
            version_id = matrix_id(f"library:{code}:v1")
            cursor.execute(
                "INSERT INTO brand_library_entries "
                "(id,tenant_id,brand_id,category,title,source_note,content,version,status,visibility_scope,updated_by,"
                "current_version_id,business_data_kind) "
                "VALUES (%s,%s,%s,'judgment',%s,%s,%s,'v1','active','headquarters',%s,NULL,'formal_business_data')",
                (entry_id, TENANT_ID, BRAND_ID, code, FOUNDER_ATTESTATION_REF, content, ADMIN_USER_ID),
            )
            cursor.execute(
                "INSERT INTO brand_library_entry_versions "
                "(id,tenant_id,brand_id,entry_id,version_number,version_label,category,title,source_note,content,"
                "visibility_scope,scope_organization_ids,created_by) "
                "VALUES (%s,%s,%s,%s,1,'v1','judgment',%s,%s,%s,'headquarters',%s,%s)",
                (
                    version_id,
                    TENANT_ID,
                    BRAND_ID,
                    entry_id,
                    code,
                    FOUNDER_ATTESTATION_REF,
                    content,
                    [organization_ids["DIYU-HQ-001"]],
                    ADMIN_USER_ID,
                ),
            )
            cursor.execute(
                "UPDATE brand_library_entries SET current_version_id=%s WHERE tenant_id=%s AND id=%s",
                (version_id, TENANT_ID, entry_id),
            )
            cursor.execute(
                "INSERT INTO brand_library_entry_organizations (id,tenant_id,entry_id,organization_id) "
                "VALUES (%s,%s,%s,%s)",
                (
                    matrix_id(f"library-scope:{code}"),
                    TENANT_ID,
                    entry_id,
                    organization_ids["DIYU-HQ-001"],
                ),
            )

    @staticmethod
    def _insert_series(
        cursor: psycopg.Cursor[dict[str, object]], contract: dict[str, Any], account_ids: dict[str, UUID]
    ) -> None:
        for series in contract["series"]:
            code = str(series["series_id"])
            account_id = account_ids[str(series["account_ids"][0])]
            cursor.execute(
                "INSERT INTO content_series "
                "(id,tenant_id,brand_id,created_by,title,premise,account_id,revision,logical_account_id,business_data_kind) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,1,%s,'formal_business_data')",
                (
                    matrix_id(f"series:{code}"),
                    TENANT_ID,
                    BRAND_ID,
                    HQ_OPERATOR_ID,
                    series["name"],
                    f"Gate A {code}；账号 {','.join(series['account_ids'])}；商品 {','.join(series['cspu_ids'])}",
                    account_id,
                    account_id,
                ),
            )

    @staticmethod
    def _insert_authorizations(
        cursor: psycopg.Cursor[dict[str, object]],
        account_ids: dict[str, UUID],
        organization_ids: dict[str, UUID],
    ) -> dict[str, tuple[UUID, str, str]]:
        contracts: dict[str, tuple[UUID, str, str]] = {}
        for subject_ref, account_code, organization_code, allowed_text in _PERSON_PUBLICATION_EXTRACTS:
            authorization_id = matrix_id(f"authorization:{subject_ref}")
            source_digest = hashlib.sha256(allowed_text.encode()).hexdigest()
            document = {
                "contract_version": "content-authorization-v1",
                "authorization_id": str(authorization_id),
                "authorization_version": "v1",
                "subject_ref": subject_ref,
                "tenant_id": str(TENANT_ID),
                "brand_id": str(BRAND_ID),
                "logical_account_id": str(account_ids[account_code]),
                "organization_id": str(organization_ids[organization_code]),
                "allowed_source_digest": source_digest,
                "allowed_usage": ["organization_people"],
                "single_use": True,
                "effective_at": "2026-08-08T00:00:00+00:00",
                "expires_at": None,
            }
            digest = hashlib.sha256(
                json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            cursor.execute(
                "INSERT INTO content_authorizations "
                "(id,tenant_id,brand_id,logical_account_id,organization_id,subject_ref,authorization_version,"
                "allowed_source_digest,allowed_usage,single_use,effective_at,expires_at,authorization_state,digest,recorded_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,'v1',%s,ARRAY['organization_people'],true,%s,NULL,'active',%s,%s)",
                (
                    authorization_id,
                    TENANT_ID,
                    BRAND_ID,
                    account_ids[account_code],
                    organization_ids[organization_code],
                    subject_ref,
                    source_digest,
                    datetime(2026, 8, 8, tzinfo=timezone.utc),
                    digest,
                    ADMIN_USER_ID,
                ),
            )
            contracts[subject_ref] = (authorization_id, digest, source_digest)
        return contracts

    def _insert_publication_projection(
        self,
        cursor: psycopg.Cursor[dict[str, object]],
        contract: dict[str, Any],
        document_ids: dict[str, tuple[UUID, UUID, str]],
        account_ids: dict[str, UUID],
        organization_ids: dict[str, UUID],
        authorization_contracts: dict[str, tuple[UUID, str, str]],
    ) -> None:
        items: list[dict[str, object]] = []
        stored: list[dict[str, object]] = []
        for position, (source_id, segment_key, role, text, authority_class) in enumerate(
            _GLOBAL_PUBLICATION_EXTRACTS, start=1
        ):
            document_id, version_id, _ = document_ids[source_id]
            segment_id = matrix_id(f"publication-segment:{segment_key}")
            source_digest = hashlib.sha256(text.encode()).hexdigest()
            cursor.execute(
                "INSERT INTO brand_source_segments "
                "(id,tenant_id,brand_id,document_id,document_version_id,segment_key,heading_path,source_locator,exact_text,"
                "semantic_kind,evidence_level,applicability,visibility_scope,digest) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'confirmed','P1-P5','brand_all',%s)",
                (
                    segment_id,
                    TENANT_ID,
                    BRAND_ID,
                    document_id,
                    version_id,
                    segment_key,
                    [source_id],
                    "Gate A frozen extraction",
                    text,
                    "creative_method" if role == "creative_method" else "expression_constraint",
                    source_digest,
                ),
            )
            item: dict[str, object] = {
                "position": position,
                "publication_role": role,
                "published_text": text,
                "applicability": [],
                "source_kind": "brand_source_segment",
                "source_ref": str(segment_id),
                "source_version": "v1",
                "source_digest": source_digest,
                "visibility_scope": "brand_all",
                "scope_organization_ids": [],
                "effective_at": datetime(2026, 8, 8, tzinfo=timezone.utc),
                "expires_at": None,
                "authority_class": authority_class,
                "semantic_subject_type": None,
                "semantic_subject_id": None,
                "claim_key": None,
                "scope_contract_version": "publication-item-scope-v2",
            }
            items.append(item)
            stored.append({"segment_id": segment_id, "item": item, "qualification": None})
        regional_document_id, regional_version_id, _ = document_ids["GATEA-SUPPLEMENT-REGIONAL-STORE-001"]
        regional_texts = self._regional_texts()
        for regional in contract["regional_store_entries"]:
            entry_code = str(regional["entry_id"])
            text = regional_texts[entry_code]
            source_digest = hashlib.sha256(text.encode()).hexdigest()
            segment_id = matrix_id(f"publication-segment:regional:{entry_code}")
            cursor.execute(
                "INSERT INTO brand_source_segments "
                "(id,tenant_id,brand_id,document_id,document_version_id,segment_key,heading_path,source_locator,exact_text,"
                "semantic_kind,evidence_level,applicability,visibility_scope,digest) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'brand_fact','confirmed','P1/P3/P4','organizations',%s)",
                (
                    segment_id,
                    TENANT_ID,
                    BRAND_ID,
                    regional_document_id,
                    regional_version_id,
                    entry_code,
                    [entry_code],
                    regional["source_anchor"],
                    text,
                    source_digest,
                ),
            )
            if regional["status"] == "fixture_gap_not_fact":
                continue
            organization_id = organization_ids[str(regional["organization_id"])]
            effective_at = datetime.fromisoformat(f"{regional['effective_at']}T00:00:00+00:00")
            expires_at = (
                datetime.fromisoformat(f"{regional['expires_at']}T00:00:00+00:00")
                if regional["expires_at"] is not None
                else None
            )
            position = len(items) + 1
            item = {
                "position": position,
                "publication_role": "public_brand_fact",
                "published_text": text,
                "applicability": ["dressing_decision", "brand_life_narrative", "local_response"],
                "source_kind": "brand_source_segment",
                "source_ref": str(segment_id),
                "source_version": str(regional["version"]),
                "source_digest": source_digest,
                "visibility_scope": "organizations",
                "scope_organization_ids": [str(organization_id)],
                "effective_at": effective_at,
                "expires_at": expires_at,
                "authority_class": "local_formal",
                "semantic_subject_type": "local_context",
                "semantic_subject_id": str(organization_id),
                "claim_key": entry_code,
                "scope_contract_version": "publication-item-scope-v2",
            }
            items.append(item)
            stored.append(
                {
                    "segment_id": segment_id,
                    "item": item,
                    "qualification": {
                        "key": entry_code,
                        "path_family": "local_trust",
                        "organization_id": organization_id,
                        "involves_person": False,
                        "authorization_id": None,
                        "authorization_digest": None,
                    },
                }
            )
        person_document_id, person_version_id, _ = document_ids["GATEA-SUPPLEMENT-PERSON-SOURCES-001"]
        for subject_ref, account_code, organization_code, text in _PERSON_PUBLICATION_EXTRACTS:
            source_digest = hashlib.sha256(text.encode()).hexdigest()
            authorization_id, authorization_digest, authorized_source_digest = authorization_contracts[subject_ref]
            if source_digest != authorized_source_digest:
                raise ValueError(f"authorization source digest mismatch: {subject_ref}")
            segment_id = matrix_id(f"publication-segment:person:{subject_ref}")
            cursor.execute(
                "INSERT INTO brand_source_segments "
                "(id,tenant_id,brand_id,document_id,document_version_id,segment_key,heading_path,source_locator,exact_text,"
                "semantic_kind,evidence_level,applicability,visibility_scope,digest) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'expression_constraint','confirmed','P3/P4',"
                "'organizations',%s)",
                (
                    segment_id,
                    TENANT_ID,
                    BRAND_ID,
                    person_document_id,
                    person_version_id,
                    subject_ref,
                    [subject_ref],
                    f"素材草案-v0/04 {subject_ref}",
                    text,
                    source_digest,
                ),
            )
            organization_id = organization_ids[organization_code]
            position = len(items) + 1
            item = {
                "position": position,
                "publication_role": "expression_constraint",
                "published_text": text,
                "applicability": ["brand_life_narrative", "local_response"],
                "source_kind": "brand_source_segment",
                "source_ref": str(segment_id),
                "source_version": "v2",
                "source_digest": source_digest,
                "visibility_scope": "organizations",
                "scope_organization_ids": [str(organization_id)],
                "effective_at": datetime(2026, 8, 8, tzinfo=timezone.utc),
                "expires_at": None,
                "authority_class": "expression_governance",
                "semantic_subject_type": None,
                "semantic_subject_id": None,
                "claim_key": None,
                "scope_contract_version": "publication-item-scope-v2",
            }
            items.append(item)
            stored.append(
                {
                    "segment_id": segment_id,
                    "item": item,
                    "qualification": {
                        "key": subject_ref,
                        "path_family": "organization_people",
                        "organization_id": organization_id,
                        "logical_account_id": account_ids[account_code],
                        "involves_person": True,
                        "authorization_id": authorization_id,
                        "authorization_digest": authorization_digest,
                    },
                }
            )
        projection_id = matrix_id("publication-projection:v2")
        digest = publication_projection_v2_digest(items)
        cursor.execute(
            "INSERT INTO brand_publication_projections "
            "(id,tenant_id,brand_id,version_number,status,digest,created_by,confirmed_by,confirmed_at,contract_version) "
            "VALUES (%s,%s,%s,2,'confirmed',%s,%s,%s,%s,'brand-publication-projection-v2')",
            (
                projection_id,
                TENANT_ID,
                BRAND_ID,
                digest,
                ADMIN_USER_ID,
                ADMIN_USER_ID,
                datetime(2026, 8, 8, tzinfo=timezone.utc),
            ),
        )
        for stored_item in stored:
            segment_id = UUID(str(stored_item["segment_id"]))
            item = cast(dict[str, object], stored_item["item"])
            position = int(cast(int, item["position"]))
            item_id = matrix_id(f"publication-item:{position}")
            cursor.execute(
                "INSERT INTO brand_publication_projection_items "
                "(id,tenant_id,brand_id,projection_id,position,publication_role,published_text,applicability,source_kind,"
                "source_segment_id,source_ref,source_version,source_digest,visibility_scope,scope_organization_ids,"
                "effective_at,expires_at,authority_class,semantic_subject_type,semantic_subject_id,claim_key,scope_contract_version) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'brand_source_segment',%s,%s,%s,%s,%s,%s,"
                "%s,%s,%s,%s,%s,%s,'publication-item-scope-v2')",
                (
                    item_id,
                    TENANT_ID,
                    BRAND_ID,
                    projection_id,
                    position,
                    item["publication_role"],
                    item["published_text"],
                    item["applicability"],
                    segment_id,
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
                ),
            )
            qualification = stored_item["qualification"]
            if isinstance(qualification, dict):
                qualification_id = matrix_id(f"qualification:{qualification['key']}")
                qualification_document = {
                    "path_family": qualification["path_family"],
                    "source_id": str(qualification_id),
                    "source_version": "v1",
                    "source_digest": item["source_digest"],
                    "organization_ref": str(qualification["organization_id"]),
                    "involves_person": qualification["involves_person"],
                    "authorization_digest": qualification["authorization_digest"],
                }
                cursor.execute(
                    "INSERT INTO brand_relevance_qualifications "
                    "(id,tenant_id,brand_id,projection_id,projection_item_id,path_family,organization_id,"
                    "involves_person,authorization_id,qualification_version,source_digest,digest) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'v1',%s,%s)",
                    (
                        qualification_id,
                        TENANT_ID,
                        BRAND_ID,
                        projection_id,
                        item_id,
                        qualification["path_family"],
                        qualification["organization_id"],
                        qualification["involves_person"],
                        qualification["authorization_id"],
                        item["source_digest"],
                        qualification_digest(qualification_document),
                    ),
                )
        cursor.execute(
            "UPDATE brands SET current_publication_projection_id=%s WHERE tenant_id=%s AND id=%s",
            (projection_id, TENANT_ID, BRAND_ID),
        )

    def inventory(self) -> dict[str, object]:
        queries = {
            "logical_roots": (
                "SELECT count(*) FROM content_accounts WHERE tenant_id=%s AND brand_id=%s AND enabled "
                "AND business_data_kind='formal_business_data' AND carrier_of_account_id IS NULL"
            ),
            "carrier_rows": (
                "SELECT count(*) FROM content_accounts WHERE tenant_id=%s AND brand_id=%s AND enabled "
                "AND business_data_kind='formal_business_data' AND carrier_of_account_id IS NOT NULL"
            ),
            "matrix_content_accounts": (
                "SELECT count(*) FROM content_accounts WHERE tenant_id=%s AND brand_id=%s AND enabled "
                "AND business_data_kind='formal_business_data'"
            ),
            "platform_format_targets": (
                "SELECT COALESCE(sum(CASE channel WHEN '抖音' THEN 1 WHEN '小红书' THEN 2 "
                "WHEN '微信视频号' THEN 1 ELSE 0 END),0) FROM content_accounts "
                "WHERE tenant_id=%s AND brand_id=%s AND enabled AND platform_enabled "
                "AND business_data_kind='formal_business_data'"
            ),
            "legacy_hidden_accounts": (
                "SELECT count(*) FROM content_accounts WHERE tenant_id=%s AND brand_id=%s AND NOT enabled "
                "AND business_data_kind='legacy_hidden'"
            ),
            "organizations": "SELECT count(*) FROM organizations WHERE tenant_id=%s AND business_data_kind='formal_business_data'",
            "regional_store_entries": (
                "SELECT count(*) FROM brand_library_entries WHERE tenant_id=%s AND brand_id=%s AND category='local_context'"
            ),
            "judgments": "SELECT count(*) FROM brand_library_entries WHERE tenant_id=%s AND brand_id=%s AND category='judgment'",
            "products": "SELECT count(*) FROM brand_products WHERE tenant_id=%s AND brand_id=%s AND source_kind='gatea_verified_visual'",
            "series": "SELECT count(*) FROM content_series WHERE tenant_id=%s AND brand_id=%s AND business_data_kind='formal_business_data'",
            "authorizations": "SELECT count(*) FROM content_authorizations WHERE tenant_id=%s AND brand_id=%s",
            "qualifications": "SELECT count(*) FROM brand_relevance_qualifications WHERE tenant_id=%s AND brand_id=%s",
            "source_documents": "SELECT count(*) FROM brand_source_documents WHERE tenant_id=%s AND brand_id=%s",
            "projection_items": (
                "SELECT count(*) FROM brand_publication_projection_items item "
                "JOIN brands brand ON brand.tenant_id=item.tenant_id AND brand.id=item.brand_id "
                "WHERE item.tenant_id=%s AND item.brand_id=%s AND item.projection_id=brand.current_publication_projection_id"
            ),
        }
        result: dict[str, object] = {}
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
            for key, query in queries.items():
                params = (TENANT_ID, BRAND_ID) if query.count("%s") == 2 else (TENANT_ID,)
                cursor.execute(query, params)
                row = cursor.fetchone()
                if row is None:
                    raise ValueError(f"inventory query returned no row: {key}")
                result[key] = int(next(iter(row.values())))
            cursor.execute(
                "SELECT array_agg(name ORDER BY name) FROM content_accounts "
                "WHERE tenant_id=%s AND brand_id=%s AND enabled AND business_data_kind='formal_business_data' "
                "AND carrier_of_account_id IS NULL",
                (TENANT_ID, BRAND_ID),
            )
            row = cursor.fetchone()
            result["active_account_names"] = list(next(iter(row.values())) or []) if row is not None else []
            cursor.execute(
                "SELECT count(*) FROM brand_library_entries WHERE tenant_id=%s AND brand_id=%s AND title='RK-EC-08' "
                "AND status='retired'",
                (TENANT_ID, BRAND_ID),
            )
            row = cursor.fetchone()
            result["expired_rk_ec_08"] = int(next(iter(row.values()))) if row is not None else 0
            cursor.execute(
                "SELECT count(*) FROM business_tasks WHERE tenant_id=%s AND brand_id=%s AND business_data_kind='legacy_hidden'",
                (TENANT_ID, BRAND_ID),
            )
            row = cursor.fetchone()
            result["legacy_tasks_readable"] = int(next(iter(row.values()))) if row is not None else 0
            cursor.execute(
                "SELECT count(*) FROM brand_publication_projection_items item "
                "JOIN brands brand ON brand.tenant_id=item.tenant_id AND brand.id=item.brand_id "
                "WHERE item.tenant_id=%s AND item.brand_id=%s "
                "AND item.projection_id=brand.current_publication_projection_id "
                "AND item.semantic_subject_type='local_context'",
                (TENANT_ID, BRAND_ID),
            )
            row = cursor.fetchone()
            result["regional_store_projection_items"] = int(next(iter(row.values()))) if row is not None else 0
        result["active_accounts"] = result["logical_roots"]
        return result


def seed_matrix_prestate(database_url: str) -> dict[str, object]:
    """Create a deterministic synthetic pre-import shape with nine legacy accounts."""

    hq_id = matrix_id("fixture:organization:hq")
    legacy_user_id = matrix_id("fixture:user:legacy")
    with psycopg.connect(database_url, row_factory=dict_row) as connection, connection.cursor() as cursor:
        cursor.execute("INSERT INTO tenants (id,name) VALUES (%s,'笛语 Gate D 隔离预演租户')", (TENANT_ID,))
        cursor.execute("INSERT INTO ops_tenant_registry (tenant_id) VALUES (%s)", (TENANT_ID,))
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", (str(TENANT_ID),))
        cursor.execute(
            "INSERT INTO organizations "
            "(id,tenant_id,name,business_data_kind,organization_level,enabled) "
            "VALUES (%s,%s,'笛语隔离前置总部','synthetic_business_fixture','company',true)",
            (hq_id, TENANT_ID),
        )
        cursor.execute(
            "INSERT INTO users (id,tenant_id,organization_id,display_name,enabled,entry_kind,business_data_kind) "
            "VALUES (%s,%s,%s,'前置态历史操作人',true,'tenant_user','synthetic_business_fixture')",
            (legacy_user_id, TENANT_ID, hq_id),
        )
        cursor.execute(
            "INSERT INTO users (id,tenant_id,organization_id,display_name,enabled,entry_kind,business_data_kind) "
            "VALUES (%s,%s,%s,'Gate D 租户管理员',true,'tenant_admin','formal_business_data')",
            (ADMIN_USER_ID, TENANT_ID, hq_id),
        )
        cursor.execute(
            "INSERT INTO tenant_management_grants (id,tenant_id,user_id,enabled) VALUES (%s,%s,%s,true)",
            (matrix_id("grant:admin"), TENANT_ID, ADMIN_USER_ID),
        )
        cursor.execute(
            "INSERT INTO brands (id,tenant_id,name,positioning,decision_order,tone,strategy_version,public_name) "
            "VALUES (%s,%s,'笛语','为家庭真实穿衣问题提供清楚而有边界的判断。',"
            "'先核现实事实，再说明取舍，最后给可执行建议。','真实、自然、具体、有判断。','v1','笛语')",
            (BRAND_ID, TENANT_ID),
        )
        cursor.execute(
            "INSERT INTO brand_audiences (id,tenant_id,brand_id,description) "
            "VALUES (%s,%s,%s,'重视真实穿衣问题、商品取舍和儿童自主感的家庭。')",
            (matrix_id("audience"), TENANT_ID, BRAND_ID),
        )
        for index in range(1, 10):
            account_id = matrix_id(f"fixture:legacy-account:{index}")
            cursor.execute(
                "INSERT INTO content_accounts "
                "(id,tenant_id,brand_id,name,channel,enabled,control_organization_id,control_organization_source,"
                "business_data_kind,platform_enabled) "
                "VALUES (%s,%s,%s,%s,'抖音',true,%s,'declared','synthetic_business_fixture',true)",
                (account_id, TENANT_ID, BRAND_ID, f"历史演示账号 {index:02d}", hq_id),
            )
        legacy_account_id = matrix_id("fixture:legacy-account:1")
        task_id = matrix_id("fixture:legacy-task")
        run_id = matrix_id("fixture:legacy-run")
        item_id = matrix_id("fixture:legacy-item")
        version_id = matrix_id("fixture:legacy-version")
        cursor.execute(
            "INSERT INTO business_tasks "
            "(id,tenant_id,brand_id,account_id,created_by,weak_seed,primary_content_product,product_refs,media_format,"
            "production_conditions,content_context_snapshot,logical_account_id,business_data_kind) "
            "VALUES (%s,%s,%s,%s,%s,'AMD 导入前历史任务','brand_life_narrative','[]','video','synthetic',%s,%s,'legacy_hidden')",
            (
                task_id,
                TENANT_ID,
                BRAND_ID,
                legacy_account_id,
                legacy_user_id,
                Jsonb({"amendment_id": "AMD-2026-0808-01", "amendment_version": "v1"}),
                legacy_account_id,
            ),
        )
        cursor.execute(
            "INSERT INTO generation_runs (id,tenant_id,task_id,model,status,completed_at,used_assets,input_receipt) "
            "VALUES (%s,%s,%s,'synthetic-prestate','succeeded',now(),'[]','{}')",
            (run_id, TENANT_ID, task_id),
        )
        cursor.execute(
            "INSERT INTO content_items (id,tenant_id,task_id,current_version) VALUES (%s,%s,%s,1)",
            (item_id, TENANT_ID, task_id),
        )
        body = "旧任务继续读取导入前 v1 口径，不被 AMD-2026-0808-01 反向改写。"
        digest = hashlib.sha256(("历史任务\n" + body).encode()).hexdigest()
        cursor.execute(
            "INSERT INTO content_versions "
            "(id,tenant_id,item_id,task_id,run_id,version_number,outline,body,created_by,artifact_digest,version_audit_snapshot) "
            "VALUES (%s,%s,%s,%s,%s,1,'历史任务',%s,%s,%s,%s)",
            (
                version_id,
                TENANT_ID,
                item_id,
                task_id,
                run_id,
                body,
                legacy_user_id,
                digest,
                Jsonb({"amendment_id": "AMD-2026-0808-01", "amendment_version": "v1"}),
            ),
        )
    return {
        "tenant_id": str(TENANT_ID),
        "brand_id": str(BRAND_ID),
        "legacy_accounts": 9,
        "legacy_task_id": str(task_id),
        "legacy_version_id": str(version_id),
    }
