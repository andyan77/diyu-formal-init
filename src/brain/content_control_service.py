from __future__ import annotations

import uuid
from collections.abc import Mapping
from uuid import UUID

from src.brain.content_expression import (
    AXIS_ORDER,
    GAP_TYPES,
    ExpressionCatalog,
    load_catalog,
    read_natural_text,
    resolve_direction,
)
from src.ports.content_control_repository import ContentControlRepository
from src.ports.material_object_store import MaterialObjectStore
from src.shared.errors import DomainError
from src.shared.types import (
    AccountExpression,
    CreativeDirection,
    ReferenceMaterial,
    TenantManagementScope,
    TrustedScope,
)

_SEGMENT_KEYS = (
    "identity_position",
    "authority_boundary",
    "audience_relationship",
    "content_territories",
    "default_production_conditions",
)
_SEGMENT_LABELS = {
    "identity_position": "表达身份",
    "authority_boundary": "真实资格与权威边界",
    "audience_relationship": "主要受众关系",
    "content_territories": "可持续经营的内容领地",
    "default_production_conditions": "可长期依赖的制作条件",
}
_DEFAULT_PRODUCTION_CONDITIONS = (
    "一名创作者、一部手机、普通室内或门店；按当前条件完成拍摄、录音、排版或剪辑。"
)
_MAX_MATERIAL_TEXT = 4000
_MAX_SELECTED_MATERIALS = 5
_UNMET_STATUSES = frozenset({"received", "classified", "answered"})

PreferenceMode = str
PREFERENCE_APPLIED = "applied"
PREFERENCE_DISABLED = "disabled"
PREFERENCE_ABSENT = "absent"
PREFERENCE_BYPASSED = "temporarily_bypassed"


class ContentControlService:
    """The minimum content control surface: catalog, account profile, private preference,
    this-task references, cold-start opportunities, a light plan and unmet-need candidates.

    Nothing here writes a business task, and no single request may quietly change the global
    catalog, brand knowledge, an account profile or somebody's private preference.
    """

    def __init__(
        self,
        repository: ContentControlRepository,
        object_store: MaterialObjectStore,
        catalog: ExpressionCatalog | None = None,
    ) -> None:
        self._repository = repository
        self._object_store = object_store
        self._catalog = catalog or load_catalog()

    @property
    def catalog(self) -> ExpressionCatalog:
        return self._catalog

    # ---- A. versioned five-axis catalog -------------------------------------------------

    def catalog_view(self, scope: TrustedScope, read_preference: bool = True) -> dict[str, object]:
        """In a temporary preference-free session the catalog is not allowed to read it either."""
        preference = self._repository.creation_preference(scope) if read_preference else None
        body_opt_in = bool(preference and preference["body_related_opt_in"])
        defaults = (
            preference["direction_defaults"] if preference and preference["enabled"] else {}
        )
        visible = self._catalog.visible(body_opt_in)
        return {
            "catalog_version": self._catalog.catalog_version,
            "body_related_enabled": body_opt_in,
            "preference_session": "bypassed" if not read_preference else "normal",
            "saved_defaults": defaults if isinstance(defaults, dict) else {},
            "axes": [
                {
                    "key": axis.key,
                    "label": axis.label,
                    "question": axis.question,
                    "options": [
                        {
                            "stable_id": entry.stable_id,
                            "label": entry.label,
                            "capability_state": entry.capability_state,
                            "body_related": entry.body_related,
                        }
                        for entry in visible
                        if entry.axis == axis.key
                    ],
                }
                for axis in self._catalog.axes
            ],
        }

    # ---- B. account expression profile --------------------------------------------------

    def account_expression(self, scope: TrustedScope) -> dict[str, object]:
        source = self._repository.expression_source(scope)
        current = self._repository.current_account_expression(scope.tenant_id, scope.account_id)
        return {
            "account": source["account_name"],
            "content_role": source["content_role_name"],
            "can_maintain": self._repository.can_maintain_account_expression(scope),
            "current": current,
            "draft": None if current else self._draft_segments(source),
            "segment_labels": dict(_SEGMENT_LABELS),
        }

    def save_account_expression(
        self, scope: TrustedScope, segments: Mapping[str, str]
    ) -> dict[str, object]:
        # The maintenance check happens inside the writing transaction, not before it.
        return self._repository.save_account_expression_as_operator(
            scope, self._checked_segments(segments)
        )

    def management_accounts(self, scope: TenantManagementScope) -> list[dict[str, object]]:
        return self._repository.management_accounts_with_expression(scope)

    def management_organizations(self, scope: TenantManagementScope) -> list[dict[str, object]]:
        return self._repository.management_organizations(scope)

    def declare_control_organization(
        self, scope: TenantManagementScope, account_id: UUID, organization_id: UUID
    ) -> dict[str, object]:
        return self._repository.declare_control_organization(scope, account_id, organization_id)

    def management_account_expression(
        self, scope: TenantManagementScope, account_id: UUID
    ) -> dict[str, object]:
        accounts = {
            str(item["id"]): item for item in self._repository.management_accounts_with_expression(scope)
        }
        account = accounts.get(str(account_id))
        if account is None:
            raise DomainError("找不到当前范围内的发布账号。")
        current = self._repository.current_account_expression(scope.tenant_id, account_id)
        return {
            "account": account["name"],
            "content_role": account["content_role"],
            "control_organization": account["control_organization"],
            "control_organization_source": account["control_organization_source"],
            "can_maintain": account["can_maintain"],
            "can_declare": account["can_declare"],
            "current": current,
            "segment_labels": dict(_SEGMENT_LABELS),
        }

    def save_management_account_expression(
        self, scope: TenantManagementScope, account_id: UUID, segments: Mapping[str, str]
    ) -> dict[str, object]:
        return self._repository.save_account_expression_as_manager(
            scope, account_id, self._checked_segments(segments)
        )

    @staticmethod
    def _checked_segments(segments: Mapping[str, str]) -> tuple[str, str, str, str, str]:
        values = tuple((segments.get(key) or "").strip() for key in _SEGMENT_KEYS)
        missing = [
            _SEGMENT_LABELS[key]
            for key, value in zip(_SEGMENT_KEYS, values, strict=True)
            if not value
        ]
        if missing:
            raise DomainError("这张画像还差：" + "、".join(missing) + "。")
        if any(len(value) > 800 for value in values):
            raise DomainError("每一段请控制在 800 字以内。")
        return (values[0], values[1], values[2], values[3], values[4])

    @staticmethod
    def _draft_segments(source: Mapping[str, str]) -> dict[str, object]:
        """A draft the person can edit; it never pretends to be the current confirmed version."""
        territory = source.get("brand_draft") or source.get("positioning") or ""
        return {
            "profile_id": None,
            "version": None,
            "is_draft": True,
            "content_role": source["content_role_name"],
            "identity_position": (
                f"{source['account_name']}代表{source['brand_name']}在{source['channel']}发声，"
                f"当前表达身份是「{source['content_role_name']}」。"
            ),
            "authority_boundary": (
                f"{source['voice_boundary']}没有已确认来源的商品、价格、库存、顾客、门店和"
                "个人经历不作为事实。"
            ),
            "audience_relationship": (
                source.get("audience_description")
                or "长期服务愿意认真挑选衣服的人；不预设年龄、身份或消费动机。"
            ),
            "content_territories": territory or "长期可持续经营的内容方向待品牌方补充。",
            "default_production_conditions": _DEFAULT_PRODUCTION_CONDITIONS,
        }

    def expression_for_generation(
        self, scope: TrustedScope, profile_id: UUID | None = None
    ) -> AccountExpression | None:
        """Return the profile a run must actually use: a frozen one when replaying, else current."""
        record = (
            self._repository.account_expression_by_id(
                scope.tenant_id, scope.account_id, profile_id
            )
            if profile_id is not None
            else self._repository.current_account_expression(scope.tenant_id, scope.account_id)
        )
        if record is None:
            return None
        version = record["version"]
        return AccountExpression(
            profile_id=UUID(str(record["profile_id"])),
            version=version if isinstance(version, int) else None,
            identity_position=str(record["identity_position"]),
            authority_boundary=str(record["authority_boundary"]),
            audience_relationship=str(record["audience_relationship"]),
            content_territories=str(record["content_territories"]),
            default_production_conditions=str(record["default_production_conditions"]),
            is_draft=False,
        )

    # ---- C. private creation preference -------------------------------------------------

    def creation_preference(self, scope: TrustedScope) -> dict[str, object]:
        preference = self._repository.creation_preference(scope)
        if preference is None:
            return {
                "exists": False,
                "enabled": False,
                "version": None,
                "direction_defaults": {},
                "collaboration_note": "",
                "body_related_opt_in": False,
                "updated_at": None,
            }
        return {"exists": True, **preference}

    def save_creation_preference(
        self,
        scope: TrustedScope,
        enabled: bool,
        direction_defaults: Mapping[str, str],
        collaboration_note: str,
        body_related_opt_in: bool,
        clear_direction_defaults: bool = False,
    ) -> dict[str, object]:
        checked: dict[str, str] = {}
        for axis, stable_id in direction_defaults.items():
            if axis not in AXIS_ORDER:
                raise DomainError("创作方向只使用固定的五个方面。")
            entry = self._catalog.entry(stable_id)
            if entry is None or entry.axis != axis:
                raise DomainError("这个创作方向当前不可选，请刷新后重新选择。")
            if entry.body_related and not body_related_opt_in:
                raise DomainError("体型相关的方向需要你先自己打开才能使用。")
            checked[axis] = stable_id
        if len(collaboration_note.strip()) > 500:
            raise DomainError("协作说明请控制在 500 字以内。")
        if not checked and not clear_direction_defaults:
            # Choosing nothing this time is not the same as asking to forget saved defaults.
            existing = self._repository.creation_preference(scope)
            existing_defaults = existing["direction_defaults"] if existing else {}
            if isinstance(existing_defaults, dict):
                checked = {str(key): str(value) for key, value in existing_defaults.items()}
        return {
            "exists": True,
            **self._repository.save_creation_preference(
                scope, enabled, checked, collaboration_note.strip(), body_related_opt_in
            ),
        }

    def delete_creation_preference(self, scope: TrustedScope) -> dict[str, object]:
        deleted = self._repository.delete_creation_preference(scope)
        return {
            "deleted": deleted,
            "message": "已删除你的私人创作偏好。系列、成品、账号画像和业务留痕都没有变化。",
        }

    # ---- D/E. this-request direction resolution -----------------------------------------

    def resolve_request_direction(
        self,
        scope: TrustedScope,
        selections: Mapping[str, str],
        custom_text: str,
        body_related_opt_in: bool,
        use_personal_preferences: bool,
        boundary_text: str,
        requested_catalog_version: str | None,
        cleared_axes: tuple[str, ...] = (),
        natural_text: str = "",
    ) -> tuple[CreativeDirection | None, PreferenceMode, int | None, str]:
        """This panel is for this task.  Saving a default is a separate, explicit action.

        A saved default is the weakest input of the three: what the person clicked now wins, then
        what this task's own words asked for, and only then the default.

        Returns the resolved direction, which preference mode applied, which preference version
        it was, and the person's own soft collaboration note when they are using preferences.
        """
        if (
            requested_catalog_version
            and requested_catalog_version != self._catalog.catalog_version
        ):
            raise DomainError("创作方向目录已更新，请刷新后重新选择。")
        if not use_personal_preferences:
            preference = None
            mode: PreferenceMode = PREFERENCE_BYPASSED
        else:
            preference = self._repository.creation_preference(scope)
            if preference is None:
                mode = PREFERENCE_ABSENT
            elif not preference["enabled"]:
                mode = PREFERENCE_DISABLED
                preference = None
            else:
                mode = PREFERENCE_APPLIED
        defaults: dict[str, str] = {}
        opt_in = body_related_opt_in
        preference_version: int | None = None
        collaboration_note = ""
        if preference is not None:
            saved = preference["direction_defaults"]
            if isinstance(saved, dict):
                defaults.update({str(key): str(value) for key, value in saved.items()})
            opt_in = opt_in or bool(preference["body_related_opt_in"])
            version = preference["version"]
            preference_version = version if isinstance(version, int) else None
            collaboration_note = str(preference["collaboration_note"])
        explicit = {key: value for key, value in selections.items() if value}
        effective_defaults = {
            axis: value for axis, value in defaults.items() if axis not in cleared_axes
        }
        steered = bool(explicit or effective_defaults or cleared_axes or custom_text.strip())
        # Nothing steered by the panel; the person's own words may still map onto a label.
        if not steered and not read_natural_text(self._catalog, natural_text).wanted:
            return None, mode, preference_version, collaboration_note
        direction = resolve_direction(
            self._catalog,
            explicit,
            custom_text,
            opt_in,
            boundary_text,
            requested_catalog_version,
            saved_defaults=defaults,
            cleared_axes=cleared_axes,
            natural_text=natural_text,
        )
        return direction, mode, preference_version, collaboration_note

    # ---- F. this-task legal references ---------------------------------------------------

    def reference_materials(
        self, scope: TrustedScope, asset_ids: tuple[UUID, ...]
    ) -> tuple[ReferenceMaterial, ...]:
        if len(asset_ids) > _MAX_SELECTED_MATERIALS:
            raise DomainError(f"这次参考最多选择 {_MAX_SELECTED_MATERIALS} 份素材。")
        selected = self._repository.selected_materials(scope, asset_ids)
        materials: list[ReferenceMaterial] = []
        for record in selected:
            media_type = str(record["media_type"])
            text_body = ""
            if media_type == "text":
                try:
                    raw = self._object_store.get(str(record["object_key"]))
                except (OSError, ValueError) as exc:
                    raise DomainError("这份文字素材暂时读不出来，请稍后再试。") from exc
                text_body = raw.decode("utf-8", errors="replace")[:_MAX_MATERIAL_TEXT]
            elif not str(record["reference_note"]).strip():
                raise DomainError("图片或视频原件需要你先写一句可读说明，系统不会自行解读画面。")
            materials.append(
                ReferenceMaterial(
                    asset_id=UUID(str(record["asset_id"])),
                    title=str(record["title"]),
                    media_type=media_type,
                    reference_version=int(str(record["reference_version"])),
                    text_body=text_body,
                    reference_note=str(record["reference_note"]),
                )
            )
        return tuple(materials)

    # ---- G. cold-start opportunities and the light plan ----------------------------------

    def opportunities(self, scope: TrustedScope, read_preference: bool = True) -> dict[str, object]:
        source = self._repository.expression_source(scope)
        current = self._repository.current_account_expression(scope.tenant_id, scope.account_id)
        profile = current or self._draft_segments(source)
        preference = self._repository.creation_preference(scope) if read_preference else None
        notes = self._repository.available_material_notes(scope)
        products = tuple(sku for sku in str(source["confirmed_product_skus"]).split(",") if sku)
        items: list[dict[str, object]] = [
            self._opportunity(
                scope,
                "identity",
                f"讲清{source['account_name']}从什么位置说话",
                f"我想讲清楚我们是谁、从什么位置说话：{profile['identity_position']}",
                {"topic": "CAT-TOPIC-PEOPLE-01", "mechanism": "CAT-GENRE-DRAMA-04"},
                "来自当前账号画像的表达身份与受众关系，不需要任何外部资料。",
            ),
            self._opportunity(
                scope,
                "audience",
                "回应受众最常见的一次穿衣处境",
                f"我想回应一次真实的穿衣处境，服务的人是：{profile['audience_relationship']}",
                {"topic": "CAT-TOPIC-OCCASION-01", "mechanism": "CAT-GENRE-TUTORIAL-01"},
                "来自当前账号画像的受众关系与已有穿衣决策能力。",
            ),
        ]
        if products:
            items.append(
                self._opportunity(
                    scope,
                    "product",
                    f"把 {products[0]} 能确认和不能下结论的部分讲清楚",
                    f"我想讲 {products[0]}：把能确认的面料或结构事实和还不能下结论的部分分开说。",
                    {"topic": "CAT-TOPIC-FABRIC-01", "mechanism": "CAT-GENRE-TUTORIAL-03"},
                    f"当前品牌已有已确认商品资料：{products[0]}。",
                )
            )
        readable = [note for note in notes if str(note["media_type"]) == "text" or str(note["reference_note"]).strip()]
        if readable:
            first = readable[0]
            items.append(
                self._opportunity(
                    scope,
                    "material",
                    f"用你已经写好的《{first['title']}》起一条",
                    f"我想用我自己的素材《{first['title']}》作为这次参考，写一条内容。",
                    {"style": "CAT-STYLE-PERSONA-04"},
                    "你已经选好的文字素材或原件说明可以直接作为本次参考。",
                    material_ids=[str(first["asset_id"])],
                )
            )
        if preference is not None and preference["enabled"] and preference["direction_defaults"]:
            defaults = preference["direction_defaults"]
            if isinstance(defaults, dict) and defaults:
                items.append(
                    self._opportunity(
                        scope,
                        "preference",
                        "按你保存的默认方向再来一条",
                        "我想按我平时的偏好方向，再做一条内容。",
                        {str(key): str(value) for key, value in defaults.items()},
                        "来自你自己保存的私人创作偏好；随时可以关闭或删除。",
                    )
                )
        return {
            "catalog_version": self._catalog.catalog_version,
            "profile_is_draft": current is None,
            "items": items,
            "boundary": "这些只是可修改的建议。点「生成当前成品」之前不会创建任何任务。",
        }

    def _opportunity(
        self,
        scope: TrustedScope,
        kind: str,
        title: str,
        seed_text: str,
        selections: Mapping[str, str],
        why: str,
        material_ids: list[str] | None = None,
    ) -> dict[str, object]:
        available = {
            axis: stable_id
            for axis, stable_id in selections.items()
            if self._catalog.entry(stable_id) is not None
        }
        return {
            "id": f"OPP-{uuid.uuid5(uuid.NAMESPACE_URL, f'{scope.account_id}:{kind}')}",
            "title": title,
            "seed_text": seed_text,
            "selections": available,
            "material_ids": material_ids or [],
            "why": why,
        }

    def plan(self, scope: TrustedScope) -> dict[str, object]:
        return self._repository.plan(scope)

    def save_plan(self, scope: TrustedScope, document: Mapping[str, object]) -> dict[str, object]:
        items = document.get("items")
        if not isinstance(items, list) or len(items) > 20:
            raise DomainError("计划最多保存 20 条，可以随时增删。")
        for item in items:
            if not isinstance(item, dict) or not str(item.get("title", "")).strip():
                raise DomainError("每一条计划都需要一句话标题。")
            if len(str(item.get("title", ""))) > 120 or len(str(item.get("note", ""))) > 500:
                raise DomainError("计划标题请控制在 120 字、备注 500 字以内。")
        return self._repository.save_plan(scope, {"items": items})

    # ---- H. unmet capability requests -----------------------------------------------------

    def create_unmet_request(
        self, scope: TrustedScope, request_text: str, direction: CreativeDirection | None
    ) -> dict[str, object]:
        text = request_text.strip()
        if not 4 <= len(text) <= 1000:
            raise DomainError("请用一两句话说明你想做但现在做不到的事。")
        snapshot: dict[str, object] = {
            "selections": (
                [
                    {"axis": item.axis, "stable_id": item.stable_id, "label": item.label}
                    for item in direction.selections
                ]
                if direction
                else []
            ),
            "custom_text": direction.custom_text if direction else "",
        }
        return self._repository.create_unmet_request(
            scope, text, self._catalog.catalog_version, snapshot
        )

    def list_unmet_requests(self, scope: TrustedScope) -> list[dict[str, object]]:
        return self._repository.list_unmet_requests(scope)

    def ops_unmet_requests(self) -> list[dict[str, object]]:
        return self._repository.ops_unmet_requests()

    def ops_classify_unmet_request(
        self, stable_request_id: str, gap_type: str, status: str, response_text: str
    ) -> dict[str, object]:
        """Classify one candidate and write back one plain answer; nothing else changes.

        A candidate never edits the catalog, brand knowledge, an account profile or somebody's
        preference — this only fills in the fields the candidate already carries.
        """
        if gap_type not in GAP_TYPES:
            raise DomainError("缺口类型不在已登记的分类里。")
        if status not in _UNMET_STATUSES:
            raise DomainError("需求候选状态不在已登记的取值里。")
        if status == "answered" and not response_text.strip():
            raise DomainError("回告状态需要写一句给提交人的回复。")
        if len(response_text.strip()) > 1000:
            raise DomainError("回告请控制在 1000 字以内。")
        tenant_id = self._repository.ops_classify_unmet_request(
            stable_request_id, gap_type, status, response_text.strip()
        )
        if tenant_id is None:
            raise DomainError("找不到这条需求候选。")
        return {
            "stable_request_id": stable_request_id,
            "tenant_id": tenant_id,
            "gap_type": gap_type,
            "status": status,
            "response_text": response_text.strip(),
        }

    # ---- F. keeping an unreadable original selectable ------------------------------------

    def set_material_reference_note(
        self, scope: TrustedScope, asset_id: UUID, reference_note: str
    ) -> dict[str, object]:
        """The one readable description of an image or video; the system still reads no bytes."""
        note = reference_note.strip()
        if not 2 <= len(note) <= 500:
            raise DomainError("请用一两句话写清楚这份原件里有什么可以参考。")
        return self._repository.set_material_reference_note(scope, asset_id, note)
