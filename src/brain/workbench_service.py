from __future__ import annotations

import csv
import hashlib
import io
from contextlib import suppress
from pathlib import Path
from uuid import UUID, uuid4

from src.brain.onboarding_prefill import (
    generic_account_profile_candidate,
    product_prefills,
)
from src.ports.material_object_store import MaterialObjectStore
from src.ports.workbench_repository import WorkbenchRepository
from src.shared.errors import DomainError
from src.shared.types import (
    DisplayScope,
    SpeakerKind,
    TenantManagementScope,
    TrustedScope,
)

_MAX_MEDIA_BYTES = 50 * 1024 * 1024


class WorkbenchService:
    def __init__(self, repository: WorkbenchRepository, object_store: MaterialObjectStore) -> None:
        self._repository = repository
        self._object_store = object_store

    def content_context(self, scope: TrustedScope, generator_mode: str) -> dict[str, object]:
        return {
            "application": "content",
            "generator_mode": generator_mode,
            "identity": self._repository.content_identity(scope),
        }

    def user_portal_context(self, scope: TrustedScope) -> dict[str, object]:
        return {
            "application": "tenant_user",
            "identity": self._repository.user_portal_identity(scope),
        }

    def tenant_management_context(self, scope: TenantManagementScope) -> dict[str, object]:
        return {
            "application": "tenant_management",
            "identity": self._repository.management_identity(scope),
        }

    def is_content_operator(self, scope: TrustedScope) -> bool:
        return self._repository.is_content_operator(scope)

    def is_tenant_manager(self, scope: TenantManagementScope) -> bool:
        return self._repository.is_tenant_manager(scope)

    def management_operators(
        self,
        scope: TenantManagementScope,
        include_archived: bool = False,
    ) -> list[dict[str, object]]:
        return self._repository.management_operators(scope, include_archived)

    def management_accounts(
        self,
        scope: TenantManagementScope,
        include_archived: bool = False,
    ) -> list[dict[str, object]]:
        return self._repository.management_accounts(scope, include_archived)

    def team_usage(
        self,
        scope: TenantManagementScope,
        window_days: int,
    ) -> dict[str, object]:
        if window_days not in {7, 30}:
            raise DomainError("团队使用情况只支持查看近 7 日或近 30 日。")
        return self._repository.team_usage(scope, window_days)

    def management_products(self, scope: TenantManagementScope) -> list[dict[str, object]]:
        return self._repository.management_products(scope)

    def management_organization_materials(
        self,
        scope: TenantManagementScope,
        owner_organization_id: UUID | None = None,
    ) -> list[dict[str, object]]:
        return self._repository.management_organization_materials(
            scope,
            owner_organization_id,
        )

    def brand_library_entries(
        self,
        scope: TenantManagementScope,
    ) -> list[dict[str, object]]:
        return self._repository.brand_library_entries(scope)

    def create_brand_library_entry(
        self,
        scope: TenantManagementScope,
        category: str,
        title: str,
        source_note: str,
        content: str,
        version: str,
        status: str,
        visibility_scope: str,
        organization_ids: tuple[UUID, ...],
    ) -> dict[str, object]:
        normalized = (
            category.strip(),
            title.strip(),
            source_note.strip(),
            content.strip(),
            version.strip(),
        )
        if not all(normalized):
            raise DomainError("资料名称、内容、自然来源说明和版本都需要填写。")
        if len(normalized[1]) > 160:
            raise DomainError("资料名称请控制在 160 个字符以内。")
        if len(normalized[2]) > 500:
            raise DomainError("自然来源说明请控制在 500 个字符以内。")
        if status not in {"candidate", "active", "retired"}:
            raise DomainError("资料状态无效。")
        if visibility_scope not in {"brand_all", "headquarters", "organizations"}:
            raise DomainError("请选择品牌全员、总部专用或指定区域。")
        unique_organizations = tuple(dict.fromkeys(organization_ids))
        if visibility_scope == "brand_all" and unique_organizations:
            raise DomainError("品牌全员资料不需要指定组织。")
        if visibility_scope == "headquarters" and len(unique_organizations) != 1:
            raise DomainError("总部专用资料需要明确选择一个公司级组织。")
        if visibility_scope == "organizations" and not unique_organizations:
            raise DomainError("指定区域资料至少需要选择一个具体区域。")
        return self._repository.create_brand_library_entry(
            scope,
            *normalized,
            status,
            visibility_scope,
            unique_organizations,
        )

    def preview_brand_library_entry(
        self,
        category: str,
        title: str,
        source_note: str,
        content: str,
        version: str,
        visibility_scope: str,
        organization_ids: tuple[UUID, ...],
    ) -> dict[str, object]:
        normalized = self._brand_library_values(
            category,
            title,
            source_note,
            content,
            version,
            visibility_scope,
            organization_ids,
        )
        return {
            "category": normalized[0],
            "title": normalized[1],
            "source_note": normalized[2],
            "content": normalized[3],
            "version": normalized[4],
            "visibility_scope": visibility_scope,
            "organization_ids": [str(item) for item in normalized[5]],
            "saved": False,
            "message": "这是导入预览；明确确认后才会保存为当前资料。",
        }

    def brand_library_entry_versions(
        self,
        scope: TenantManagementScope,
        entry_id: UUID,
    ) -> list[dict[str, object]]:
        return self._repository.brand_library_entry_versions(scope, entry_id)

    def save_brand_library_entry_version(
        self,
        scope: TenantManagementScope,
        entry_id: UUID,
        title: str,
        source_note: str,
        content: str,
        version: str,
        visibility_scope: str,
        organization_ids: tuple[UUID, ...],
    ) -> dict[str, object]:
        normalized = self._brand_library_values(
            "reference",
            title,
            source_note,
            content,
            version,
            visibility_scope,
            organization_ids,
        )
        return self._repository.save_brand_library_entry_version(
            scope,
            entry_id,
            normalized[1],
            normalized[2],
            normalized[3],
            normalized[4],
            visibility_scope,
            normalized[5],
        )

    def set_brand_library_entry_enabled(
        self,
        scope: TenantManagementScope,
        entry_id: UUID,
        enabled: bool,
    ) -> dict[str, object]:
        return self._repository.set_brand_library_entry_enabled(
            scope,
            entry_id,
            enabled,
        )

    def add_management_organization_material(
        self,
        scope: TenantManagementScope,
        organization_id: UUID,
        title: str,
        filename: str,
        content_type: str,
        payload: bytes,
        declares_identifiable_minor: bool,
        reference_note: str,
        visibility_scope: str = "organizations",
        organization_ids: tuple[UUID, ...] = (),
        exact_owner_scope: bool = False,
    ) -> dict[str, object]:
        if declares_identifiable_minor:
            raise DomainError("第一版不能保存认得出真人未成年人的照片、视频或声音。")
        if not title.strip() or len(title.strip()) > 120:
            raise DomainError("素材名称需要在 1 到 120 个字符之间。")
        if len(payload) == 0 or len(payload) > _MAX_MEDIA_BYTES:
            raise DomainError("素材文件为空或超过首期 50MB 上限。")
        if len(reference_note.strip()) > 500:
            raise DomainError("原件说明请控制在 500 字以内。")
        media_type = self._media_type(content_type)
        if media_type in {"image", "video"} and len(reference_note.strip()) < 2:
            raise DomainError("图片或视频请先写一句人工说明。")
        if visibility_scope not in {"brand_all", "headquarters", "organizations"}:
            raise DomainError("请选择品牌全员、总部专用或指定区域。")
        unique_organizations = tuple(dict.fromkeys(organization_ids))
        if visibility_scope == "brand_all" and unique_organizations:
            raise DomainError("品牌全员素材不需要指定可用组织。")
        if visibility_scope == "headquarters" and len(unique_organizations) != 1:
            raise DomainError("总部专用素材需要明确选择一个公司级组织。")
        if visibility_scope == "organizations" and not unique_organizations:
            unique_organizations = (organization_id,)
        suffix = Path(filename).suffix
        asset_id = uuid4()
        try:
            object_key = self._object_store.put(asset_id, suffix, payload)
            return self._repository.create_management_organization_material(
                scope,
                organization_id,
                asset_id,
                title.strip(),
                media_type,
                object_key,
                len(payload),
                filename,
                hashlib.sha256(payload).hexdigest(),
                reference_note.strip(),
                visibility_scope,
                unique_organizations,
                exact_owner_scope,
            )
        except (OSError, ValueError) as exc:
            if "object_key" in locals():
                self._delete_after_failed_metadata_write(object_key)
            raise DomainError("素材原件暂时无法保存，请检查文件后重试。") from exc
        except DomainError:
            if "object_key" in locals():
                self._delete_after_failed_metadata_write(object_key)
            raise

    def delete_management_organization_material(
        self,
        scope: TenantManagementScope,
        asset_id: UUID,
        owner_organization_id: UUID | None = None,
    ) -> None:
        object_key = self._repository.request_management_material_deletion(
            scope,
            asset_id,
            owner_organization_id,
        )
        try:
            self._object_store.delete(object_key)
            self._repository.finalize_management_material_deletion(
                scope,
                asset_id,
                owner_organization_id,
            )
        except (OSError, ValueError) as exc:
            raise DomainError("素材删除尚未完成；当前记录已标记为待删除，可直接重试。") from exc

    def management_material_versions(
        self,
        scope: TenantManagementScope,
        asset_id: UUID,
        owner_organization_id: UUID | None = None,
    ) -> list[dict[str, object]]:
        return self._repository.management_material_versions(
            scope,
            asset_id,
            owner_organization_id,
        )

    def save_management_material_version(
        self,
        scope: TenantManagementScope,
        asset_id: UUID,
        title: str,
        reference_note: str,
        visibility_scope: str,
        organization_ids: tuple[UUID, ...],
        owner_organization_id: UUID | None = None,
    ) -> dict[str, object]:
        if not title.strip() or len(title.strip()) > 120:
            raise DomainError("素材名称需要在 1 到 120 个字符之间。")
        if not reference_note.strip() or len(reference_note.strip()) > 500:
            raise DomainError("请填写 1 到 500 字的人工说明。")
        unique_organizations = self._scope_organizations(
            visibility_scope,
            organization_ids,
            "素材",
        )
        return self._repository.save_management_material_version(
            scope,
            asset_id,
            title.strip(),
            reference_note.strip(),
            visibility_scope,
            unique_organizations,
            owner_organization_id,
        )

    def set_management_material_enabled(
        self,
        scope: TenantManagementScope,
        asset_id: UUID,
        enabled: bool,
        owner_organization_id: UUID | None = None,
    ) -> dict[str, object]:
        return self._repository.set_management_material_enabled(
            scope,
            asset_id,
            enabled,
            owner_organization_id,
        )

    def management_product_media_bindings(
        self,
        scope: TenantManagementScope,
        asset_id: UUID,
    ) -> list[dict[str, object]]:
        return self._repository.management_product_media_bindings(
            scope,
            asset_id,
        )

    def create_management_product_media_binding(
        self,
        scope: TenantManagementScope,
        asset_id: UUID,
        product_id: UUID,
    ) -> dict[str, object]:
        return self._repository.create_management_product_media_binding(
            scope,
            asset_id,
            product_id,
        )

    def set_management_product_media_binding_enabled(
        self,
        scope: TenantManagementScope,
        asset_id: UUID,
        binding_id: UUID,
        enabled: bool,
    ) -> dict[str, object]:
        return self._repository.set_management_product_media_binding_enabled(
            scope,
            asset_id,
            binding_id,
            enabled,
        )

    def management_demo_content_index(self, scope: TenantManagementScope) -> dict[str, object]:
        return self._repository.management_demo_content_index(scope)

    def management_onboarding_prefill(
        self,
        scope: TenantManagementScope,
    ) -> dict[str, object]:
        identity = self._repository.management_identity(scope)
        product_drafts, metadata = product_prefills(identity["brand"])
        accounts = self._repository.management_accounts(scope)
        confirmed_skus = {str(item["sku"]) for item in self._repository.management_products(scope)}
        pending_products = [item for item in product_drafts if str(item.get("sku") or "") not in confirmed_skus]
        carrier_drafts = self._platform_carrier_prefills(accounts) if metadata else []
        return {
            **metadata,
            "account_profile_candidate": generic_account_profile_candidate(identity["brand"]),
            "account_profile_candidate_source": (
                "基于当前租户名称、已确认品牌表达边界和通用企业账号冷启动规则生成；保存前必须由管理员纠正。"
            ),
            "product_drafts": pending_products,
            "platform_carrier_drafts": carrier_drafts,
        }

    def save_management_product(
        self,
        scope: TenantManagementScope,
        sku: str,
        display_name: str,
        category: str,
        colors: tuple[str, ...],
        material_or_structure: str,
        silhouette: str,
        observable_features: str,
        source_note: str,
        applicability: str,
        confirm_as_current_brand_fact: bool,
        as_synthetic_business_fixture: bool = False,
        visibility_scope: str = "brand_all",
        organization_ids: tuple[UUID, ...] = (),
        display_family: str | None = None,
        display_is_long: bool = False,
        display_accent: bool = False,
    ) -> dict[str, object]:
        if not confirm_as_current_brand_fact:
            raise DomainError("请先纠正草案，并明确确认它是当前品牌商品事实。")
        if not sku.strip() or not display_name.strip():
            raise DomainError("商品编号和商品名称需要填写。")
        if not source_note.strip() or not applicability.strip():
            raise DomainError("请保留资料来源说明，并说明这版事实适用于什么范围。")
        facts: dict[str, object] = {
            key: value
            for key, value in (
                ("category", category.strip()),
                ("colors", [item.strip() for item in colors if item.strip()]),
                ("material_or_structure", material_or_structure.strip()),
                ("silhouette", silhouette.strip()),
                ("observable_features", observable_features.strip()),
                ("display_family", display_family),
                ("is_long", display_is_long if display_family == "upper" else False),
                ("accent", display_accent if display_family == "upper" else False),
            )
            if value not in (None, "", [], False)
        }
        if display_family not in {None, "upper", "lower"}:
            raise DomainError("陈列位置只能选择上杆或下杆。")
        if not facts:
            raise DomainError("请至少填写一项本轮内容实际需要的商品事实。")
        if visibility_scope not in {"brand_all", "headquarters", "organizations"}:
            raise DomainError("请选择品牌全员、总部专用或指定区域。")
        unique_organizations = tuple(dict.fromkeys(organization_ids))
        if visibility_scope == "brand_all" and unique_organizations:
            raise DomainError("品牌全员商品资料不需要指定组织。")
        if visibility_scope == "headquarters" and len(unique_organizations) != 1:
            raise DomainError("总部专用商品资料需要明确选择一个公司级组织。")
        if visibility_scope == "organizations" and not unique_organizations:
            raise DomainError("指定区域商品资料至少需要选择一个具体区域。")
        return self._repository.save_management_product(
            scope,
            sku.strip(),
            display_name.strip(),
            facts,
            ("synthetic_business_fixture" if as_synthetic_business_fixture else "brand_user_confirmed"),
            source_note.strip(),
            applicability.strip(),
            visibility_scope,
            unique_organizations,
        )

    def preview_product_import(
        self,
        source_format: str,
        content: str,
    ) -> dict[str, object]:
        if source_format not in {"table", "csv"}:
            raise DomainError("商品导入只支持粘贴表格或 CSV。")
        delimiter = "\t" if source_format == "table" else ","
        rows = list(csv.DictReader(io.StringIO(content), delimiter=delimiter))
        if not rows or len(rows) > 100:
            raise DomainError("导入内容需要包含表头和 1 到 100 行商品。")
        required = {"sku", "display_name"}
        if not required.issubset(rows[0]):
            raise DomainError("导入表格至少需要 sku 和 display_name 两列。")
        preview: list[dict[str, object]] = []
        for row in rows:
            sku = str(row.get("sku") or "").strip()
            display_name = str(row.get("display_name") or "").strip()
            if not sku or not display_name:
                raise DomainError("每一行都需要商品编号和商品名称。")
            preview.append(
                {
                    "sku": sku,
                    "display_name": display_name,
                    "category": str(row.get("category") or "").strip(),
                    "material_or_structure": str(row.get("material_or_structure") or "").strip(),
                    "silhouette": str(row.get("silhouette") or "").strip(),
                    "observable_features": str(row.get("observable_features") or "").strip(),
                }
            )
        return {
            "rows": preview,
            "saved": False,
            "message": "这是字段预览；每件商品明确确认后才会保存。",
        }

    def management_product_versions(
        self,
        scope: TenantManagementScope,
        sku: str,
    ) -> list[dict[str, object]]:
        return self._repository.management_product_versions(
            scope,
            sku.strip(),
        )

    def set_management_product_enabled(
        self,
        scope: TenantManagementScope,
        sku: str,
        enabled: bool,
    ) -> dict[str, object]:
        return self._repository.set_management_product_enabled(
            scope,
            sku.strip(),
            enabled,
        )

    @staticmethod
    def _platform_carrier_prefills(
        accounts: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        channels = {
            "抖音": "douyin_video",
            "小红书": "xiaohongshu_graphic",
            "微信视频号": "wechat_channels_video",
        }
        roots: dict[str, dict[str, object]] = {}
        for account in accounts:
            root_id = str(account.get("carrier_of_account_id") or account["id"])
            if account.get("carrier_of_account_id") is None:
                roots[root_id] = {
                    "account": account,
                    "targets": set(),
                }
            root = roots.setdefault(
                root_id,
                {
                    "account": account,
                    "targets": set(),
                },
            )
            raw_target_set = root["targets"]
            if not isinstance(raw_target_set, set):
                continue
            channel = str(account.get("channel") or "")
            channel_target = channels.get(channel)
            if channel_target:
                raw_target_set.add(channel_target)
            raw_targets = account.get("platform_targets")
            targets = raw_targets if isinstance(raw_targets, list) else []
            for target in targets:
                if not isinstance(target, dict):
                    continue
                value = str(target.get("target") or target.get("value") or "")
                if value:
                    raw_target_set.add(value)

        drafts: list[dict[str, object]] = []
        for root in roots.values():
            root_account = root["account"]
            if not isinstance(root_account, dict):
                continue
            operators = root_account.get("operators")
            checked_operators = operators if isinstance(operators, list) else []
            only_operator = checked_operators[0] if len(checked_operators) == 1 else None
            raw_target_set = root["targets"]
            existing_targets = raw_target_set if isinstance(raw_target_set, set) else set()
            for channel, target in channels.items():
                if target in existing_targets:
                    continue
                drafts.append(
                    {
                        "source_account_id": str(root_account["id"]),
                        "source_account_name": str(root_account["name"]),
                        "name": f"{root_account['name']}·{channel}",
                        "channel": channel,
                        "operator_id": (str(only_operator.get("id") or "") if isinstance(only_operator, dict) else ""),
                        "operator_name": (
                            str(only_operator.get("display_name") or "") if isinstance(only_operator, dict) else ""
                        ),
                    }
                )
        return drafts

    def create_publishing_account(
        self,
        scope: TenantManagementScope,
        name: str,
        channel: str,
        content_role_name: str,
        voice_boundary: str | None,
        operator_id: UUID | None = None,
        control_organization_id: UUID | None = None,
        operator_can_maintain_expression_profile: bool = False,
        as_synthetic_business_fixture: bool = False,
        initial_profile: dict[str, str] | None = None,
        speaker_kind: SpeakerKind = "unknown",
    ) -> dict[str, object]:
        normalized_profile = (
            {key: value.strip() for key, value in initial_profile.items()} if initial_profile is not None else None
        )
        if normalized_profile is not None and (
            set(normalized_profile)
            != {
                "identity_position",
                "authority_boundary",
                "audience_relationship",
                "content_territories",
                "default_production_conditions",
            }
            or not all(normalized_profile.values())
        ):
            raise DomainError("请一次填写完整的五段账号画像。")
        if (
            normalized_profile is not None
            and voice_boundary is not None
            and voice_boundary.strip() != normalized_profile["authority_boundary"]
        ):
            raise DomainError("账号画像的权威边界与内部账号类型边界不一致。")
        resolved_boundary = (
            normalized_profile["authority_boundary"]
            if normalized_profile is not None
            else (voice_boundary or "").strip()
        )
        values = (
            name.strip(),
            channel.strip(),
            content_role_name.strip(),
            resolved_boundary,
        )
        if not all(values):
            raise DomainError("发布账号、账号类型短标签和账号画像都需要填写。")
        if normalized_profile is not None and control_organization_id is None:
            raise DomainError("建立账号画像前，请先明确负责团队。")
        if operator_id is None and operator_can_maintain_expression_profile:
            raise DomainError("请在成员与资格中明确授予五段画像维护资格。")
        return self._repository.create_publishing_account(
            scope,
            *values,
            operator_id,
            control_organization_id,
            operator_can_maintain_expression_profile,
            ("synthetic_business_fixture" if as_synthetic_business_fixture else "formal_business_data"),
            normalized_profile,
            speaker_kind,
        )

    def update_publishing_speaker_kind(
        self,
        scope: TenantManagementScope,
        account_id: UUID,
        speaker_kind: SpeakerKind,
    ) -> dict[str, object]:
        return self._repository.update_publishing_speaker_kind(
            scope,
            account_id,
            speaker_kind,
        )

    def update_publishing_account(
        self,
        scope: TenantManagementScope,
        account_id: UUID,
        name: str | None,
        control_organization_id: UUID | None,
    ) -> dict[str, object]:
        normalized_name = name.strip() if name is not None else None
        if name is not None and not normalized_name:
            raise DomainError("发布账号名称不能为空。")
        if normalized_name is None and control_organization_id is None:
            raise DomainError("请至少修改账号名称或负责团队。")
        return self._repository.update_publishing_account(
            scope,
            account_id,
            normalized_name,
            control_organization_id,
        )

    def set_publishing_account_enabled(
        self,
        scope: TenantManagementScope,
        account_id: UUID,
        enabled: bool,
    ) -> dict[str, object]:
        return self._repository.set_publishing_account_enabled(
            scope,
            account_id,
            enabled,
        )

    def create_platform_carrier(
        self,
        scope: TenantManagementScope,
        source_account_id: UUID,
        name: str,
        channel: str,
        confirm_internal_carrier: bool,
        operator_id: UUID | None = None,
    ) -> dict[str, object]:
        if not confirm_internal_carrier:
            raise DomainError("请先确认这只是内部内容载体，不会连接或登录真实平台。")
        if not name.strip() or not channel.strip():
            raise DomainError("平台版本载体需要账号名称和目标平台。")
        return self._repository.create_platform_carrier(
            scope,
            source_account_id,
            name.strip(),
            channel.strip(),
            operator_id,
        )

    def set_platform_carrier_enabled(
        self,
        scope: TenantManagementScope,
        account_id: UUID,
        enabled: bool,
    ) -> dict[str, object]:
        return self._repository.set_platform_carrier_enabled(
            scope,
            account_id,
            enabled,
        )

    def create_operator(
        self,
        scope: TenantManagementScope,
        display_name: str,
        account_id: UUID,
        default_persona_name: str = "",
        default_persona_boundary: str = "",
    ) -> dict[str, object]:
        if not display_name.strip():
            raise DomainError("请先填写实际操作者的自然人姓名或工作名。")
        if bool(default_persona_name.strip()) != bool(default_persona_boundary.strip()):
            raise DomainError("默认表达人设需要同时说明名称和成立边界。")
        return self._repository.create_operator(
            scope,
            display_name.strip(),
            account_id,
            default_persona_name.strip(),
            default_persona_boundary.strip(),
        )

    def update_default_persona(self, scope: TrustedScope, name: str, boundary: str) -> dict[str, object]:
        if not name.strip() or not boundary.strip():
            raise DomainError("本人默认表达人设需要名称和成立边界。")
        return self._repository.update_default_persona(scope, name.strip(), boundary.strip())

    def display_context(self, scope: DisplayScope, generator_mode: str) -> dict[str, object]:
        return {
            "application": "display",
            "generator_mode": generator_mode,
            "identity": self._repository.display_identity(scope),
        }

    def management_display_stores(
        self,
        scope: TenantManagementScope,
    ) -> list[dict[str, object]]:
        return self._repository.management_display_stores(scope)

    def save_management_display_store(
        self,
        scope: TenantManagementScope,
        store_id: UUID | None,
        name: str,
        control_organization_id: UUID,
        execution_organization_id: UUID,
        upper_comfort_capacity: int,
        lower_comfort_capacity: int,
    ) -> dict[str, object]:
        return self._repository.save_management_display_store(
            scope,
            store_id,
            name.strip(),
            control_organization_id,
            execution_organization_id,
            {
                "schema": "dm01-wall-double-rail-v1",
                "upper_comfort_capacity": upper_comfort_capacity,
                "lower_comfort_capacity": lower_comfort_capacity,
            },
        )

    def set_management_display_store_enabled(
        self,
        scope: TenantManagementScope,
        store_id: UUID,
        enabled: bool,
    ) -> dict[str, object]:
        return self._repository.set_management_display_store_enabled(
            scope,
            store_id,
            enabled,
        )

    def recent_content(self, scope: TrustedScope) -> list[dict[str, object]]:
        return self._repository.recent_content(scope)

    def content_versions(self, scope: TrustedScope, task_id: UUID) -> list[dict[str, object]]:
        return self._repository.content_versions(scope, task_id)

    def recent_display(self, scope: DisplayScope) -> list[dict[str, object]]:
        return self._repository.recent_display(scope)

    def display_versions(self, scope: DisplayScope, task_id: UUID) -> list[dict[str, object]]:
        return self._repository.display_versions(scope, task_id)

    def readiness(self, scope: TenantManagementScope) -> dict[str, object]:
        items = self._repository.readiness(scope)
        by_id = {str(item["id"]): item for item in items}
        inputs = self._repository.tenant_readiness_inputs(scope)
        source_document_count = inputs.get("source_documents")
        product_media_count = inputs.get("product_media_products")
        confirmed_store_count = inputs.get("confirmed_stores")
        if not all(
            isinstance(value, int)
            for value in (
                source_document_count,
                product_media_count,
                confirmed_store_count,
            )
        ):
            raise DomainError("当前品牌资料就绪条件无效。")
        assert isinstance(source_document_count, int)
        assert isinstance(product_media_count, int)
        assert isinstance(confirmed_store_count, int)

        def tenant_item(
            item_id: str,
            title: str,
            state: str,
            evidence: list[str],
            missing: list[str],
            impact: str,
            unaffected: str,
            action: str,
            section: str,
        ) -> dict[str, object]:
            return {
                "id": item_id,
                "title": title,
                "state": state,
                "evidence": evidence,
                "missing": missing,
                "impact": impact,
                "unaffected": unaffected,
                "action": {"label": action, "section": section},
            }

        expression_ready = str(by_id.get("non_product_content", {}).get("status")) == "available"
        product_ready = str(by_id.get("product_facts", {}).get("status")) == "available"
        platform_ready = str(by_id.get("platform_recompile", {}).get("status")) == "available"
        series_ready = str(by_id.get("continuous_series", {}).get("status")) == "available"
        first_ready = str(by_id.get("first_creation", {}).get("status")) == "available"
        dm01_ready = str(by_id.get("dm01_display", {}).get("status")) == "available"
        source_ready = source_document_count > 0
        visual_ready = product_media_count >= 2
        tenant_items = [
            tenant_item(
                "tenant_non_product",
                "普通非商品内容",
                "ready" if expression_ready and source_ready else "ready_after_admin_action",
                [f"已授权品牌源文档：{source_document_count} 份"],
                [] if expression_ready and source_ready else ["确认品牌资料与可操作账号。"],
                "决定品牌日常表达是否有稳定依据。",
                "不影响管理员维护成员、组织和资料。",
                "查看品牌资料",
                "brand-library",
            ),
            tenant_item(
                "tenant_product_content",
                "商品承重 P1 / P2",
                "ready" if product_ready else "data_missing",
                ["只使用当前商品版本中获准进入事实包的字段。"],
                [] if product_ready else ["补充至少一件有 V 级可观察依据的商品。"],
                "只影响需要具体商品承担判断或解释的内容。",
                "不影响非商品内容。",
                "查看商品资料",
                "brand-library",
            ),
            tenant_item(
                "tenant_life_content",
                "P3 生活与账号内容",
                "ready" if expression_ready and source_ready else "ready_after_admin_action",
                ["账号画像与品牌表达边界独立进入创作。"],
                [] if expression_ready and source_ready else ["确认账号画像和品牌表达资料。"],
                "影响生活片段如何形成该账号自己的表达。",
                "不要求商品或门店资料。",
                "管理发布账号",
                "publishing-accounts",
            ),
            tenant_item(
                "tenant_local_content",
                "P4 门店内容",
                "ready" if confirmed_store_count > 0 else "data_missing",
                [f"已确认门店档案：{confirmed_store_count} 份"],
                [] if confirmed_store_count > 0 else ["当前没有品牌确认的真实门店档案。"],
                "只影响需要门店或本地服务事实的内容。",
                "用户明确提供的单次观察仍可按其原话创作。",
                "建立门店档案",
                "members",
            ),
            tenant_item(
                "tenant_visual_content",
                "P5 商品视觉",
                "ready" if visual_ready else "data_missing",
                [f"具备正式媒体绑定的商品：{product_media_count} 件"],
                [] if visual_ready else ["至少为两件不同商品登记并明确选择真实图片或视频。"],
                "只影响以商品视觉关系为主价值的成品。",
                "不影响 P1—P4 与纯文字内容。",
                "补充组织官方素材",
                "brand-library",
            ),
            tenant_item(
                "tenant_series",
                "连续系列",
                "ready" if series_ready else "ready_after_admin_action",
                ["系列前情会随任务冻结。"],
                [] if series_ready else ["先完成一个可操作发布账号和画像。"],
                "影响连续内容的前情承接。",
                "不影响单条内容。",
                "管理发布账号",
                "publishing-accounts",
            ),
            tenant_item(
                "tenant_dm01",
                "纯文字陈列参考方案",
                "ready" if dm01_ready else "data_missing",
                [f"已确认门店档案：{confirmed_store_count} 份"],
                [] if dm01_ready else ["补齐真实门店档案、陈列资格与本次库存。"],
                "只影响 DM01 文字参考方案。",
                "不影响内容创作。",
                "建立门店档案",
                "members",
            ),
            tenant_item(
                "tenant_platforms",
                "平台与形式",
                "ready" if platform_ready else "ready_after_admin_action",
                ["同一逻辑账号跨平台共享同一画像。"],
                [] if platform_ready else ["为逻辑账号补充平台与形式目标。"],
                "影响可选择的平台原生成品形式。",
                "不改变登录身份或账号画像。",
                "管理平台目标",
                "publishing-accounts",
            ),
            tenant_item(
                "tenant_first_creation",
                "新成员首次创作",
                "ready" if first_ready else "ready_after_admin_action",
                ["成员需获得可操作发布账号。"],
                [] if first_ready else ["创建成员并分配发布账号资格。"],
                "影响新成员能否从一句话开始创作。",
                "不影响现有管理员维护资料。",
                "管理成员",
                "members",
            ),
        ]
        return {
            "brand_name": str(inputs["brand_name"]),
            "software_truth": {
                "usable": 58,
                "defective": 0,
                "placeholder": 0,
                "not_built": 6,
                "unproven": 0,
            },
            "items": items,
            "tenant_data_items": tenant_items,
        }

    def brand_expression(self, scope: TenantManagementScope) -> dict[str, object]:
        return self._repository.brand_expression(scope)

    def confirm_brand_expression(self, scope: TenantManagementScope, draft: str) -> dict[str, object]:
        if len(draft.strip()) < 8:
            raise DomainError("请先留下足以判断表达方向的一句话。")
        return self._repository.confirm_brand_expression(scope, draft.strip())

    def list_series(self, scope: TrustedScope) -> list[dict[str, object]]:
        return self._repository.list_series(scope)

    def create_series(self, scope: TrustedScope, title: str, premise: str) -> dict[str, object]:
        if not title.strip():
            raise DomainError("请先给这组连续内容一个名称。")
        return self._repository.create_series(scope, title.strip(), premise.strip())

    def add_series_item(
        self, scope: TrustedScope, series_id: UUID, task_id: UUID, position: int | None
    ) -> dict[str, object]:
        return self._repository.add_series_item(scope, series_id, task_id, position)

    def reorder_series(self, scope: TrustedScope, series_id: UUID, task_ids: tuple[UUID, ...]) -> dict[str, object]:
        return self._repository.reorder_series(scope, series_id, task_ids)

    def reset_series(self, scope: TrustedScope, series_id: UUID) -> dict[str, object]:
        return self._repository.reset_series(scope, series_id)

    def list_materials(self, scope: TrustedScope) -> list[dict[str, object]]:
        return self._repository.list_materials(scope)

    def add_material(
        self,
        scope: TrustedScope,
        asset_scope: str,
        title: str,
        filename: str,
        content_type: str,
        payload: bytes,
        declares_identifiable_minor: bool,
        reference_note: str = "",
    ) -> dict[str, object]:
        if declares_identifiable_minor:
            raise DomainError("第一版不能保存认得出真人未成年人的照片、视频或声音。")
        if asset_scope not in {"personal", "organization"}:
            raise DomainError("素材入口无效。")
        if asset_scope == "organization" and not self._repository.is_material_maintainer(scope):
            raise DomainError("你目前没有维护组织素材的权限。可以继续使用已授权素材。")
        if not title.strip() or len(title.strip()) > 120:
            raise DomainError("素材名称需要在 1 到 120 个字符之间。")
        if len(payload) == 0 or len(payload) > _MAX_MEDIA_BYTES:
            raise DomainError("素材文件为空或超过首期 50MB 上限。")
        if len(reference_note.strip()) > 500:
            raise DomainError("原件说明请控制在 500 字以内。")
        media_type = self._media_type(content_type)
        suffix = Path(filename).suffix
        asset_id = uuid4()
        try:
            object_key = self._object_store.put(asset_id, suffix, payload)
            return self._repository.create_material(
                scope,
                asset_id,
                title.strip(),
                media_type,
                asset_scope,
                object_key,
                len(payload),
                filename,
                hashlib.sha256(payload).hexdigest(),
                reference_note.strip(),
            )
        except (OSError, ValueError) as exc:
            if "object_key" in locals():
                self._delete_after_failed_metadata_write(object_key)
            raise DomainError("素材原件暂时无法保存，请检查文件后重试。") from exc
        except DomainError:
            if "object_key" in locals():
                self._delete_after_failed_metadata_write(object_key)
            raise

    def delete_material(self, scope: TrustedScope, asset_id: UUID) -> None:
        object_key = self._repository.request_material_deletion(scope, asset_id)
        try:
            self._object_store.delete(object_key)
            self._repository.finalize_material_deletion(scope, asset_id)
        except (OSError, ValueError) as exc:
            raise DomainError("素材删除尚未完成；当前记录已标记为待删除，可直接重试。") from exc

    def _delete_after_failed_metadata_write(self, object_key: str) -> None:
        with suppress(OSError, ValueError):
            self._object_store.delete(object_key)

    @staticmethod
    def _scope_organizations(
        visibility_scope: str,
        organization_ids: tuple[UUID, ...],
        subject: str,
    ) -> tuple[UUID, ...]:
        if visibility_scope not in {"brand_all", "headquarters", "organizations"}:
            raise DomainError("请选择品牌全员、总部专用或指定区域。")
        unique = tuple(dict.fromkeys(organization_ids))
        if visibility_scope == "brand_all" and unique:
            raise DomainError(f"品牌全员{subject}不需要指定组织。")
        if visibility_scope == "headquarters" and len(unique) != 1:
            raise DomainError(f"总部专用{subject}需要明确选择一个公司级组织。")
        if visibility_scope == "organizations" and not unique:
            raise DomainError(f"指定区域{subject}至少需要选择一个具体区域。")
        return unique

    @classmethod
    def _brand_library_values(
        cls,
        category: str,
        title: str,
        source_note: str,
        content: str,
        version: str,
        visibility_scope: str,
        organization_ids: tuple[UUID, ...],
    ) -> tuple[str, str, str, str, str, tuple[UUID, ...]]:
        normalized = (
            category.strip(),
            title.strip(),
            source_note.strip(),
            content.strip(),
            version.strip(),
        )
        if not all(normalized):
            raise DomainError("资料名称、内容、自然来源说明和版本都需要填写。")
        if len(normalized[1]) > 160:
            raise DomainError("资料名称请控制在 160 个字符以内。")
        if len(normalized[2]) > 500:
            raise DomainError("自然来源说明请控制在 500 个字符以内。")
        unique = cls._scope_organizations(
            visibility_scope,
            organization_ids,
            "资料",
        )
        return (*normalized, unique)

    @staticmethod
    def _media_type(content_type: str) -> str:
        if content_type.startswith("image/"):
            return "image"
        if content_type.startswith("video/"):
            return "video"
        if content_type.startswith("text/"):
            return "text"
        raise DomainError("第一版只保存文字、图片或视频原件作为创作参考。")
