from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from src.brain.content_control_service import (
    PREFERENCE_ABSENT,
    PREFERENCE_BYPASSED,
    ContentControlService,
)
from src.brain.content_expression import direction_from_snapshot, snapshot_document
from src.brain.natural_entry import (
    is_natural_chat,
    natural_reply,
    requests_continuation,
    sanitize_seed,
)
from src.brain.p1_contract import assert_content_complete
from src.brain.platform_directions import direction_for, target_from_text
from src.ports.content_generator import ContentGenerator
from src.ports.content_repository import ContentRepository
from src.shared.content_snapshot import frozen_series_context
from src.shared.errors import DomainError, GenerationFailed
from src.shared.types import (
    AccountExpression,
    ActiveAsset,
    BrandContext,
    ContentControlContext,
    ContentProduct,
    ContentTarget,
    GenerationInput,
    PlatformDirection,
    ProductFact,
    ReferenceMaterial,
    RequestedControls,
    RoutingInput,
    SeriesContext,
    TrustedScope,
)

_NO_FROZEN_CONTEXT = (
    "这条历史内容没有保留完整的创作条件，请按当前输入新建一条。"
)
_MISSING_FROZEN_MATERIAL = (
    "这条内容当时用到的参考素材已经不可用，请按当前输入新建一条。"
)
_MISSING_FROZEN_PROFILE = (
    "这条内容当时用到的账号表达画像已经读不到了，请按当前输入新建一条。"
)


class ContentService:
    def __init__(
        self,
        repository: ContentRepository,
        generator: ContentGenerator,
        control_service: ContentControlService | None = None,
    ) -> None:
        self._repository = repository
        self._generator = generator
        self._control = control_service

    def create_from_weak_seed(
        self,
        scope: TrustedScope,
        weak_seed: str,
        reuse_version_id: UUID | None = None,
        target: ContentTarget = "douyin_video",
        controls: RequestedControls | None = None,
        series_id: UUID | None = None,
        series_position: int | None = None,
    ) -> dict[str, object]:
        if reuse_version_id is None and is_natural_chat(weak_seed):
            return {"kind": "greeting", "message": natural_reply()}
        if series_position is not None and series_id is None:
            raise DomainError("指定系列集数前，请先选择一个系列。")
        continuation = (
            reuse_version_id is None
            and series_id is None
            and requests_continuation(weak_seed)
        )
        if continuation:
            reuse_version_id = self._repository.latest_visible_version(scope)
            if reuse_version_id is None:
                return {"kind": "greeting", "message": "还没有当前账号可继续的上一条内容。"}
        sanitized_seed = sanitize_seed(weak_seed)
        natural_target = target_from_text(sanitized_seed)
        target = natural_target or target
        direction = direction_for(target)
        production_conditions = self._production_conditions(sanitized_seed, direction.media_format)
        context = self._repository.load_brand_context(
            scope, direction.media_format, production_conditions
        )
        self._assert_target_context(context, direction.platform)
        series_context = (
            self._series_context(scope, series_id, series_position, sanitized_seed)
            if series_id is not None
            else None
        )
        primary_product: ContentProduct | None
        is_recompile = False
        if reuse_version_id is not None:
            source = self._repository.load_recompile_source(scope, reuse_version_id)
            if (
                continuation
                and source.source_target == target
                and not self._requests_independent_result(sanitized_seed)
            ):
                return self.revise(scope, source.task_id, sanitized_seed, target)
            products = source.products
            prior_body = source.body
            if self._requests_independent_result(sanitized_seed):
                primary_product = self._generator.route(
                    RoutingInput(sanitized_seed, context, products, prior_body)
                )
                source_description = None
            else:
                primary_product = source.primary_product
                is_recompile = source.source_target != target
                source_description = source.source_description if is_recompile else None
        else:
            products = self._repository.load_product_facts(scope, sanitized_seed)
            if not products and self._requires_confirmed_product(
                sanitized_seed, context.brand_name
            ):
                return {
                    "kind": "question",
                    "message": "要讲当前品牌的具体商品，请先指定一件已经确认资料的商品。",
                }
            series_prior = (
                series_context.prior_entries[-1].body
                if series_context is not None and series_context.prior_entries
                else None
            )
            primary_product = self._generator.route(
                RoutingInput(sanitized_seed, context, products, series_prior)
            )
            prior_body = None
            source_description = None
        if primary_product is None:
            return {"kind": "greeting", "message": natural_reply()}
        if primary_product == "product_truth" and not products:
            return {
                "kind": "question",
                "message": "这条商品解释要以哪件当前品牌已确认商品为依据？",
            }
        if primary_product == "visual_styling_story" and not products:
            return {"kind": "question", "message": "这条视觉内容要以哪件当前品牌商品为锚？"}
        assets = self._repository.load_active_assets(
            scope, primary_product, sanitized_seed, products, target, is_recompile
        )
        control = self._control_context(scope, context, controls, sanitized_seed)
        task_id, run_id, prior_body = self._repository.create_task_and_running_run(
            scope,
            sanitized_seed,
            primary_product,
            reuse_version_id,
            self._generator.model_name,
            assets,
            context,
            products,
            target,
            direction.media_format,
            direction,
            source_description,
            production_conditions,
            control,
            snapshot_document(
                control,
                context.content_role_name,
                products,
                series_context,
            ),
            series_context,
        )
        return self._generate_and_persist(
            scope,
            task_id,
            run_id,
            sanitized_seed,
            primary_product,
            None,
            prior_body,
            context,
            assets,
            products,
            target,
            direction,
            source_description,
            control,
            series_context,
        )

    def _control_context(
        self,
        scope: TrustedScope,
        context: BrandContext,
        controls: RequestedControls | None,
        natural_text: str = "",
    ) -> ContentControlContext:
        """Resolve this request's own control choices against server-trusted brand boundaries."""
        if self._control is None:
            return ContentControlContext(
                catalog_version=None,
                direction=None,
                account_expression=None,
                materials=(),
                preference_mode=PREFERENCE_ABSENT,
                preference_version=None,
                content_role=context.content_role_name,
                content_role_boundary=context.content_role_boundary,
            )
        requested = controls or RequestedControls()
        boundary_text = " ".join(
            (context.tone, context.content_role_boundary, context.positioning, context.decision_order)
        )
        (
            creative,
            preference_mode,
            preference_version,
            collaboration_note,
        ) = self._control.resolve_request_direction(
            scope,
            dict(requested.selections),
            requested.custom_text,
            requested.body_related_opt_in,
            requested.use_personal_preferences,
            boundary_text,
            requested.catalog_version,
            cleared_axes=requested.cleared_axes,
            natural_text=natural_text,
        )
        return ContentControlContext(
            catalog_version=self._control.catalog.catalog_version,
            direction=creative,
            account_expression=self._control.expression_for_generation(scope),
            materials=self._control.reference_materials(scope, requested.material_ids),
            preference_mode=preference_mode,
            preference_version=preference_version,
            content_role=context.content_role_name,
            content_role_boundary=context.content_role_boundary,
            collaboration_note=collaboration_note,
        )

    def _replayed_control(
        self, scope: TrustedScope, snapshot: dict[str, object]
    ) -> ContentControlContext:
        """A revision reads its own frozen conditions; today's settings never stand in."""
        profile_id = snapshot.get("account_expression_profile_id")
        expression = None
        frozen_expression = snapshot.get("account_expression")
        if isinstance(frozen_expression, dict):
            raw_version = frozen_expression.get("version")
            expression = AccountExpression(
                profile_id=(
                    UUID(str(frozen_expression["profile_id"]))
                    if frozen_expression.get("profile_id")
                    else None
                ),
                version=raw_version if isinstance(raw_version, int) else None,
                identity_position=str(frozen_expression.get("identity_position") or ""),
                authority_boundary=str(frozen_expression.get("authority_boundary") or ""),
                audience_relationship=str(
                    frozen_expression.get("audience_relationship") or ""
                ),
                content_territories=str(frozen_expression.get("content_territories") or ""),
                default_production_conditions=str(
                    frozen_expression.get("default_production_conditions") or ""
                ),
                is_draft=False,
            )
        elif self._control is not None and isinstance(profile_id, str) and profile_id:
            expression = self._control.expression_for_generation(scope, UUID(profile_id))
            if expression is None:
                raise DomainError(_MISSING_FROZEN_PROFILE)
        material_refs = snapshot.get("material_refs")
        frozen_versions: dict[UUID, int] = {}
        if isinstance(material_refs, list):
            frozen_versions = {
                UUID(str(item["asset_id"])): int(str(item.get("reference_version", 1)))
                for item in material_refs
                if isinstance(item, dict) and item.get("asset_id")
            }
        materials: tuple[ReferenceMaterial, ...] = ()
        if self._control is not None and frozen_versions:
            try:
                materials = self._control.reference_materials(scope, tuple(frozen_versions))
            except DomainError as exc:
                raise DomainError(_MISSING_FROZEN_MATERIAL) from exc
            # A reference that moved on is not the reference this task froze.
            if any(
                frozen_versions[item.asset_id] != item.reference_version for item in materials
            ):
                raise DomainError(_MISSING_FROZEN_MATERIAL)
        catalog_version = snapshot.get("catalog_version")
        preference_version = snapshot.get("private_preference_version")
        frozen_role = snapshot.get("content_role")
        frozen_boundary = snapshot.get("content_role_boundary")
        return ContentControlContext(
            catalog_version=str(catalog_version) if isinstance(catalog_version, str) else None,
            direction=direction_from_snapshot(snapshot),
            account_expression=expression,
            materials=materials,
            preference_mode=str(snapshot.get("private_preference_mode") or PREFERENCE_ABSENT),
            preference_version=(
                preference_version if isinstance(preference_version, int) else None
            ),
            content_role=str(frozen_role) if isinstance(frozen_role, str) else "",
            content_role_boundary=(
                str(frozen_boundary) if isinstance(frozen_boundary, str) else ""
            ),
            # A revision replays conditions; it never reads today's private preference.
            collaboration_note="",
        )

    @staticmethod
    def _replayed_context(context: BrandContext, control: ContentControlContext) -> BrandContext:
        """Speak from the identity this task froze, not from whatever the account carries today.

        Renaming the account's expression identity, or rewriting its boundary, changes what the
        next new task says.  It must not silently rewrite the identity an existing task and all
        of its later versions were produced under.
        """
        if not control.content_role:
            return context
        return replace(
            context,
            content_role_name=control.content_role,
            content_role_boundary=control.content_role_boundary or context.content_role_boundary,
        )

    @staticmethod
    def _requires_confirmed_product(seed: str, brand_name: str) -> bool:
        """Fail closed only for an explicit current-brand factual product request."""
        product_subject = any(
            marker in seed
            for marker in ("商品", "外套", "上衣", "裤子", "裙子", "连衣裙", "鞋", "这件", "这款")
        )
        current_brand = any(
            marker in seed
            for marker in (brand_name, "当前品牌", "你们品牌", "我们品牌")
        )
        factual_request = any(
            marker in seed
            for marker in (
                "面料",
                "成分",
                "价格",
                "库存",
                "工艺",
                "功能",
                "最值得买",
                "哪件",
                "推荐一件",
                "讲一件",
            )
        )
        return product_subject and current_brand and factual_request

    def revise(
        self,
        scope: TrustedScope,
        task_id: UUID,
        instruction: str,
        target: ContentTarget = "douyin_video",
    ) -> dict[str, object]:
        direction = direction_for(target)
        snapshot = self._repository.load_content_context_snapshot(scope, task_id)
        if snapshot is None:
            return {"kind": "question", "message": _NO_FROZEN_CONTEXT}
        weak_seed, primary_product, media_format, prior_conditions = self._repository.task_details(
            scope, task_id
        )
        if media_format != direction.media_format:
            raise GenerationFailed("改换图文或平台请从当前版本选择目标并新建改编版本")
        production_conditions = self._production_conditions(
            instruction, media_format, prior_conditions
        )
        context = self._repository.load_brand_context(scope, media_format, production_conditions)
        self._assert_target_context(context, direction.platform)
        products = self._repository.load_task_product_facts(scope, task_id)
        assets = self._repository.load_active_assets(
            scope, primary_product, instruction, products, target, False
        )
        control = self._replayed_control(scope, snapshot)
        series_context = frozen_series_context(snapshot)
        context = self._replayed_context(context, control)
        run_id, parent_version_id, weak_seed, primary_product = self._repository.revise_task(
            scope,
            task_id,
            instruction,
            self._generator.model_name,
            assets,
            context,
            products,
            target,
            direction,
            production_conditions,
            control,
            series_context,
        )
        return self._generate_and_persist(
            scope,
            task_id,
            run_id,
            weak_seed,
            primary_product,
            instruction,
            self._repository.fetch_version_body(scope, parent_version_id),
            context,
            assets,
            products,
            target,
            direction,
            None,
            control,
            series_context,
        )

    def fetch_version(self, scope: TrustedScope, task_id: UUID, version: int) -> dict[str, object]:
        return self._repository.fetch_version(scope, task_id, version)

    def save_version(self, scope: TrustedScope, version_id: UUID) -> dict[str, object]:
        return self._repository.save_version(scope, version_id)

    def recompile_task(
        self,
        source_scope: TrustedScope,
        target_scope: TrustedScope,
        task_id: UUID,
        instruction: str,
        target: ContentTarget,
        controls: RequestedControls | None = None,
    ) -> dict[str, object]:
        """Recompile one frozen source version for an explicitly resolved platform carrier."""
        del controls
        source_version_id = self._repository.latest_task_version(source_scope, task_id)
        source = self._repository.load_recompile_source(source_scope, source_version_id)
        snapshot = self._repository.load_content_context_snapshot(source_scope, source.task_id)
        if snapshot is None:
            return {"kind": "question", "message": _NO_FROZEN_CONTEXT}
        direction = direction_for(target)
        production_conditions = self._production_conditions(
            instruction, direction.media_format
        )
        context = self._repository.load_brand_context(
            target_scope, direction.media_format, production_conditions
        )
        self._assert_target_context(context, direction.platform)
        control = self._replayed_control(source_scope, snapshot)
        control = self._recompile_control(control)
        context = self._replayed_context(context, control)
        series_context = frozen_series_context(snapshot)
        assets = self._repository.load_active_assets(
            target_scope,
            source.primary_product,
            instruction,
            source.products,
            target,
            True,
        )
        target_task_id, run_id, prior_body = self._repository.create_task_and_running_run(
            target_scope,
            source.weak_seed,
            source.primary_product,
            source_version_id,
            self._generator.model_name,
            assets,
            context,
            source.products,
            target,
            direction.media_format,
            direction,
            source.source_description,
            production_conditions,
            control,
            snapshot_document(
                control,
                control.content_role or context.content_role_name,
                source.products,
                series_context,
            ),
            None,
        )
        return self._generate_and_persist(
            target_scope,
            target_task_id,
            run_id,
            source.weak_seed,
            source.primary_product,
            instruction,
            prior_body,
            context,
            assets,
            source.products,
            target,
            direction,
            source.source_description,
            control,
            series_context,
        )

    def identity_summary(
        self, scope: TrustedScope, target: ContentTarget = "douyin_video"
    ) -> dict[str, str]:
        direction = direction_for(target)
        context = self._repository.load_brand_context(
            scope,
            direction.media_format,
            self._production_conditions("", direction.media_format),
        )
        return {
            "brand": context.brand_name,
            "operator": context.operator_name,
            "organization": context.organization_name,
            "account": context.account_name,
            "content_role": context.content_role_name,
            "platform": context.platform,
            "media_format": context.media_format,
        }

    def _generate_and_persist(
        self,
        scope: TrustedScope,
        task_id: UUID,
        run_id: UUID,
        weak_seed: str,
        primary_product: ContentProduct,
        revision_instruction: str | None,
        prior_saved_body: str | None,
        context: BrandContext,
        assets: tuple[ActiveAsset, ...],
        products: tuple[ProductFact, ...],
        target: ContentTarget,
        direction: PlatformDirection,
        source_version_description: str | None,
        control: ContentControlContext | None = None,
        series_context: SeriesContext | None = None,
    ) -> dict[str, object]:
        try:
            artifact = self._generator.generate(
                GenerationInput(
                    run_id=run_id,
                    task_id=task_id,
                    weak_seed=weak_seed,
                    primary_product=primary_product,
                    revision_instruction=revision_instruction,
                    brand=context,
                    target=target,
                    media_format=direction.media_format,
                    platform_direction=direction,
                    active_domain_assets=assets,
                    products=products,
                    prior_saved_body=prior_saved_body,
                    source_version_description=source_version_description,
                    creative_direction=control.direction if control else None,
                    account_expression=control.account_expression if control else None,
                    reference_materials=control.materials if control else (),
                    collaboration_note=control.collaboration_note if control else "",
                    series_context=series_context,
                )
            )
            assert_content_complete(artifact)
        except GenerationFailed as exc:
            self._repository.fail_run(scope, task_id, run_id, str(exc))
            raise
        except Exception as exc:  # Provider implementation details never reach the user.
            self._repository.fail_run(scope, task_id, run_id, "模型调用失败，请稍后重试")
            raise GenerationFailed("模型调用失败，请稍后重试") from exc
        except BaseException:
            # Cancellation and process-level interruption must not leave a durable
            # generation run looking active after the request slot is released.
            self._repository.fail_run(scope, task_id, run_id, "模型调用已取消")
            raise
        completed = self._repository.complete_run_with_version(
            scope,
            task_id,
            run_id,
            artifact.outline,
            artifact.body,
            artifact.model,
            artifact.latency_ms,
            artifact.retry_count,
            artifact.provider_usage,
            {key: str(value) for key, value in vars(artifact.semantic_contract).items()},
            artifact.fact_repair_receipts,
        )
        version_value = completed["version"]
        if not isinstance(version_value, int):
            raise GenerationFailed("内容版本数据无效")
        visible = self._repository.fetch_version(scope, task_id, version_value)
        creative = control.direction if control else None
        return completed | {
            "kind": "content",
            "ai_generated": visible["ai_generated"],
            "aigc_label": visible["aigc_label"],
            "aigc_release_reminder": visible["aigc_release_reminder"],
            "target": visible["target"],
            "target_key": visible["target_key"],
            "adapted_from": visible["adapted_from"],
            # Shown before the artifact, never inside it, and never a review report.
            "translation_notice": creative.translation_notice if creative else None,
            "applied_direction": (
                [item.applied_label for item in creative.selections] if creative else []
            ),
        }

    def _series_context(
        self,
        scope: TrustedScope,
        series_id: UUID,
        position: int | None,
        natural_text: str,
    ) -> SeriesContext:
        context = self._repository.load_series_context(scope, series_id, position)
        return replace(
            context,
            user_asserted_published_continuity=any(
                marker in natural_text
                for marker in (
                    "上一期已经",
                    "上一集已经",
                    "上期已经",
                    "之前发布",
                    "上一期讲过",
                    "上一集讲过",
                )
            ),
        )

    @staticmethod
    def _recompile_control(control: ContentControlContext) -> ContentControlContext:
        """Carry task choices across platforms without reapplying a private saved default."""
        direction = control.direction
        if direction is None:
            return control
        selections = tuple(item for item in direction.selections if item.origin != "default")
        replayed_direction = (
            replace(
                direction,
                selections=selections,
                translation_notice=(
                    direction.translation_notice
                    if any(item.translated for item in selections)
                    else None
                ),
            )
            if selections or direction.custom_text
            else None
        )
        return replace(
            control,
            direction=replayed_direction,
            preference_mode=PREFERENCE_BYPASSED,
            preference_version=None,
            collaboration_note="",
        )

    @staticmethod
    def _production_conditions(text: str, media_format: str, previous: str | None = None) -> str:
        if "8 秒" in text or "8秒" in text:
            return "目标自然时长为 8 秒；无法同时保留原有全部认知时，只做明确标识的窄主题版，不称与原版等义。"
        if "四张" in text or "4 张" in text or "4张" in text:
            return "当前只补拍四张；图文仍须有完整正文，并由正文保留商品归因边界。"
        if "一个人" in text or "一人" in text or "手机" in text:
            return "一名创作者、一部手机、普通室内或门店；按当前形式完成拍摄、录音、排版或剪辑。"
        if previous is not None:
            return previous
        if media_format == "graphic":
            return "一名创作者、一部手机、普通室内或门店；按当前条件补拍、选图、排版并发布图文。"
        return "一名创作者、一部手机、普通室内或门店；按当前条件完成拍摄、录音和剪辑。"

    @staticmethod
    def _requests_independent_result(text: str) -> bool:
        return any(marker in text for marker in ("另外", "独立", "单独拍", "单独用", "另一条"))

    @staticmethod
    def _assert_target_context(context: BrandContext, platform: str) -> None:
        if context.platform != platform:
            raise DomainError("当前可信内容身份不能使用该目标平台")
