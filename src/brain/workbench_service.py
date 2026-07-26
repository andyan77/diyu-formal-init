from __future__ import annotations

import hashlib
from contextlib import suppress
from pathlib import Path
from uuid import UUID, uuid4

from src.brain.onboarding_prefill import product_prefills
from src.ports.material_object_store import MaterialObjectStore
from src.ports.workbench_repository import WorkbenchRepository
from src.shared.errors import DomainError
from src.shared.types import DisplayScope, TenantManagementScope, TrustedScope

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

    def management_operators(self, scope: TenantManagementScope) -> list[dict[str, object]]:
        return self._repository.management_operators(scope)

    def management_accounts(self, scope: TenantManagementScope) -> list[dict[str, object]]:
        return self._repository.management_accounts(scope)

    def management_products(self, scope: TenantManagementScope) -> list[dict[str, object]]:
        return self._repository.management_products(scope)

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
            )
            if value
        }
        if not facts:
            raise DomainError("请至少填写一项本轮内容实际需要的商品事实。")
        return self._repository.save_management_product(
            scope,
            sku.strip(),
            display_name.strip(),
            facts,
            (
                "synthetic_business_fixture"
                if as_synthetic_business_fixture
                else "brand_user_confirmed"
            ),
            source_note.strip(),
            applicability.strip(),
        )

    @staticmethod
    def _platform_carrier_prefills(
        accounts: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        channels = ("抖音", "小红书", "微信视频号")
        existing = {
            (str(item.get("carrier_of_account_id") or ""), str(item["channel"]))
            for item in accounts
            if item.get("carrier_of_account_id")
        }
        drafts: list[dict[str, object]] = []
        for account in accounts:
            if account.get("carrier_of_account_id"):
                continue
            operators = account.get("operators")
            checked_operators = operators if isinstance(operators, list) else []
            only_operator = checked_operators[0] if len(checked_operators) == 1 else None
            for channel in channels:
                if (
                    channel == str(account["channel"])
                    or (
                        str(account["id"]),
                        channel,
                    )
                    in existing
                ):
                    continue
                drafts.append(
                    {
                        "source_account_id": str(account["id"]),
                        "source_account_name": str(account["name"]),
                        "name": str(account["name"]),
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
        voice_boundary: str,
        operator_id: UUID,
        control_organization_id: UUID | None = None,
        operator_can_maintain_expression_profile: bool = False,
        as_synthetic_business_fixture: bool = False,
    ) -> dict[str, object]:
        values = (name.strip(), channel.strip(), content_role_name.strip(), voice_boundary.strip())
        if not all(values):
            raise DomainError("发布账号、独立表达身份和成立边界都需要填写。")
        return self._repository.create_publishing_account(
            scope,
            *values,
            operator_id,
            control_organization_id,
            operator_can_maintain_expression_profile,
            (
                "synthetic_business_fixture"
                if as_synthetic_business_fixture
                else "formal_business_data"
            ),
        )

    def create_platform_carrier(
        self,
        scope: TenantManagementScope,
        source_account_id: UUID,
        name: str,
        channel: str,
        operator_id: UUID,
        confirm_internal_carrier: bool,
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

    def recent_content(self, scope: TrustedScope) -> list[dict[str, object]]:
        return self._repository.recent_content(scope)

    def content_versions(self, scope: TrustedScope, task_id: UUID) -> list[dict[str, object]]:
        return self._repository.content_versions(scope, task_id)

    def recent_display(self, scope: DisplayScope) -> list[dict[str, object]]:
        return self._repository.recent_display(scope)

    def display_versions(self, scope: DisplayScope, task_id: UUID) -> list[dict[str, object]]:
        return self._repository.display_versions(scope, task_id)

    def readiness(self, scope: TenantManagementScope) -> dict[str, object]:
        return {"items": self._repository.readiness(scope)}

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
    def _media_type(content_type: str) -> str:
        if content_type.startswith("image/"):
            return "image"
        if content_type.startswith("video/"):
            return "video"
        if content_type.startswith("text/"):
            return "text"
        raise DomainError("第一版只保存文字、图片或视频原件作为创作参考。")
