from __future__ import annotations

import re
from collections.abc import Callable
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
from src.brain.platform_directions import direction_for
from src.ports.content_generator import ContentGenerator
from src.ports.content_repository import ContentRepository
from src.shared.content_snapshot import (
    frozen_series_context,
    frozen_system_creative_plan,
    frozen_user_actuality_quotes,
    frozen_user_premise,
)
from src.shared.errors import DomainError, GenerationFailed
from src.shared.types import (
    AccountExpression,
    ActiveAsset,
    BrandContext,
    ContentControlContext,
    ContentProduct,
    ContentTarget,
    ConversationDecision,
    ConversationInput,
    ConversationTurn,
    GenerationInput,
    PlatformDirection,
    ProductFact,
    ReferenceMaterial,
    RequestedControls,
    RoutingInput,
    SeriesContext,
    TrustedScope,
)

_NO_FROZEN_CONTEXT = "这条历史内容没有保留完整的创作条件，请按当前输入新建一条。"
_MISSING_FROZEN_MATERIAL = "这条内容当时用到的参考素材已经不可用，请按当前输入新建一条。"
_MISSING_FROZEN_PROFILE = "这条内容当时用到的账号表达画像已经读不到了，请按当前输入新建一条。"


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
        primary_product_override: ContentProduct | None = None,
        progress: Callable[[str], None] | None = None,
        user_actuality_quotes: tuple[str, ...] | None = None,
        system_creative_plan: str = "",
    ) -> dict[str, object]:
        if primary_product_override is None and reuse_version_id is None and is_natural_chat(weak_seed):
            return {"kind": "greeting", "message": natural_reply()}
        if series_position is not None and series_id is None:
            raise DomainError("指定系列集数前，请先选择一个系列。")
        continuation = reuse_version_id is None and series_id is None and requests_continuation(weak_seed)
        if continuation:
            reuse_version_id = self._repository.latest_visible_version(scope)
            if reuse_version_id is None:
                return {"kind": "greeting", "message": "还没有当前账号可继续的上一条内容。"}
        sanitized_seed = sanitize_seed(weak_seed)
        sanitized_actualities = (
            tuple(sanitize_seed(item) for item in user_actuality_quotes)
            if user_actuality_quotes is not None
            else None
        )
        sanitized_plan = sanitize_seed(system_creative_plan)
        direction = direction_for(target)
        production_conditions = self._production_conditions(sanitized_seed, direction.media_format)
        context = self._repository.load_brand_context(scope, direction.media_format, production_conditions)
        self._assert_target_context(context, direction.platform)
        series_context = (
            self._series_context(scope, series_id, series_position, sanitized_seed) if series_id is not None else None
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
                primary_product = self._generator.route(RoutingInput(sanitized_seed, context, products, prior_body))
                source_description = None
            else:
                primary_product = source.primary_product
                is_recompile = source.source_target != target
                source_description = source.source_description if is_recompile else None
        else:
            products = self._repository.load_product_facts(scope, sanitized_seed)
            if not products and self._requires_confirmed_product(sanitized_seed, context.brand_name):
                return {
                    "kind": "question",
                    "message": "要讲当前品牌的具体商品，请先指定一件已经确认资料的商品。",
                }
            series_prior = (
                series_context.prior_entries[-1].body
                if series_context is not None and series_context.prior_entries
                else None
            )
            primary_product = primary_product_override or self._generator.route(
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
                context.business_data_kind,
                context.brand_reference_context,
                sanitized_seed,
                sanitized_actualities,
                sanitized_plan,
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
            progress,
            sanitized_actualities,
            sanitized_plan,
        )

    def respond_to_conversation(
        self,
        scope: TrustedScope,
        message: str,
        history: tuple[ConversationTurn, ...],
        target: ContentTarget,
        controls: RequestedControls | None = None,
        series_id: UUID | None = None,
        series_position: int | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> dict[str, object]:
        """Collaborate without persistence until one request is genuinely generation-ready."""
        sanitized_message = sanitize_seed(message)
        sanitized_history = tuple(ConversationTurn(turn.role, sanitize_seed(turn.content)) for turn in history[-8:])
        if (
            sanitized_history
            and sanitized_history[-1].role == "user"
            and sanitized_history[-1].content == sanitized_message
        ):
            sanitized_history = sanitized_history[:-1]
        if not sanitized_history and is_natural_chat(sanitized_message):
            return {"kind": "chat", "message": natural_reply()}
        if progress is not None:
            progress("compiling_context")
        direction = direction_for(target)
        production_conditions = self._production_conditions(sanitized_message, direction.media_format)
        context = self._repository.load_brand_context(scope, direction.media_format, production_conditions)
        self._assert_target_context(context, direction.platform)
        combined_text = "\n".join(
            [
                *(turn.content for turn in sanitized_history if turn.role == "user"),
                sanitized_message,
            ]
        )
        products = self._repository.load_product_facts(scope, combined_text)
        control = self._control_context(scope, context, controls, combined_text)
        selected_direction = ""
        if control.direction is not None:
            selected_direction = "；".join(
                [
                    *(f"{item.axis}：{item.applied_label}" for item in control.direction.selections),
                    *((f"自然补充：{control.direction.custom_text}",) if control.direction.custom_text else ()),
                ]
            )
        series_summary = ""
        if series_id is not None:
            series = self._series_context(scope, series_id, series_position, combined_text)
            series_summary = (
                f"系列《{series.title}》第 {series.target_position} 个位置；"
                f"已有 {len(series.prior_entries)} 条必要前情。"
            )
        decision: ConversationDecision = self._generator.collaborate(
            ConversationInput(
                message=sanitized_message,
                history=sanitized_history,
                brand=context,
                products=products,
                target=target,
                selected_direction=selected_direction,
                prior_series_summary=series_summary,
            )
        )
        if decision.disposition != "ready":
            return {
                "kind": decision.disposition,
                "message": decision.message,
            }
        if (
            decision.primary_product is None
            or not decision.user_premises
            or not decision.system_creative_plan
        ):
            raise GenerationFailed("这次还没能整理成可靠的创作要求，请继续补充一句。")
        user_premise = "\n".join(decision.user_premises)
        result = self.create_from_weak_seed(
            scope,
            user_premise,
            target=target,
            controls=controls,
            series_id=series_id,
            series_position=series_position,
            primary_product_override=decision.primary_product,
            progress=progress,
            user_actuality_quotes=decision.user_actuality_quotes,
            system_creative_plan=decision.system_creative_plan,
        )
        return result | {"conversation_message": decision.message}

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

    def _replayed_control(self, scope: TrustedScope, snapshot: dict[str, object]) -> ContentControlContext:
        """A revision reads its own frozen conditions; today's settings never stand in."""
        profile_id = snapshot.get("account_expression_profile_id")
        expression = None
        frozen_expression = snapshot.get("account_expression")
        if isinstance(frozen_expression, dict):
            raw_version = frozen_expression.get("version")
            expression = AccountExpression(
                profile_id=(
                    UUID(str(frozen_expression["profile_id"])) if frozen_expression.get("profile_id") else None
                ),
                version=raw_version if isinstance(raw_version, int) else None,
                identity_position=str(frozen_expression.get("identity_position") or ""),
                authority_boundary=str(frozen_expression.get("authority_boundary") or ""),
                audience_relationship=str(frozen_expression.get("audience_relationship") or ""),
                content_territories=str(frozen_expression.get("content_territories") or ""),
                default_production_conditions=str(frozen_expression.get("default_production_conditions") or ""),
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
            if any(frozen_versions[item.asset_id] != item.reference_version for item in materials):
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
            preference_version=(preference_version if isinstance(preference_version, int) else None),
            content_role=str(frozen_role) if isinstance(frozen_role, str) else "",
            content_role_boundary=(str(frozen_boundary) if isinstance(frozen_boundary, str) else ""),
            # A revision replays conditions; it never reads today's private preference.
            collaboration_note="",
        )

    @staticmethod
    def _replayed_context(
        context: BrandContext,
        control: ContentControlContext,
        snapshot: dict[str, object] | None = None,
    ) -> BrandContext:
        """Speak from the identity this task froze, not from whatever the account carries today.

        Renaming the account's expression identity, or rewriting its boundary, changes what the
        next new task says.  It must not silently rewrite the identity an existing task and all
        of its later versions were produced under.
        """
        raw_references = snapshot.get("brand_reference_context") if snapshot is not None else None
        frozen_references = (
            tuple(str(item) for item in raw_references if isinstance(item, str))
            if isinstance(raw_references, list)
            else context.brand_reference_context
        )
        if not control.content_role:
            return replace(context, brand_reference_context=frozen_references)
        return replace(
            context,
            content_role_name=control.content_role,
            content_role_boundary=control.content_role_boundary or context.content_role_boundary,
            brand_reference_context=frozen_references,
        )

    @staticmethod
    def _requires_confirmed_product(seed: str, brand_name: str) -> bool:
        """Fail closed only for an explicit current-brand factual product request."""
        product_subject = any(
            marker in seed for marker in ("商品", "外套", "上衣", "裤子", "裙子", "连衣裙", "鞋", "这件", "这款")
        )
        current_brand = any(marker in seed for marker in (brand_name, "当前品牌", "你们品牌", "我们品牌"))
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
        (
            weak_seed,
            primary_product,
            media_format,
            prior_conditions,
            source_description,
        ) = self._repository.task_details(scope, task_id)
        if media_format != direction.media_format:
            raise GenerationFailed("改换图文或平台请从当前版本选择目标并新建改编版本")
        production_conditions = self._production_conditions(instruction, media_format, prior_conditions)
        context = self._repository.load_brand_context(scope, media_format, production_conditions)
        self._assert_target_context(context, direction.platform)
        products = self._repository.load_task_product_facts(scope, task_id)
        user_premise = frozen_user_premise(snapshot, weak_seed)
        user_actuality_quotes = frozen_user_actuality_quotes(snapshot)
        system_creative_plan = frozen_system_creative_plan(snapshot)
        assets = self._repository.load_active_assets(
            scope,
            primary_product,
            instruction,
            products,
            target,
            source_description is not None,
        )
        control = self._replayed_control(scope, snapshot)
        series_context = frozen_series_context(snapshot)
        context = self._replayed_context(context, control, snapshot)
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
            source_description,
        )
        return self._generate_and_persist(
            scope,
            task_id,
            run_id,
            user_premise,
            primary_product,
            instruction,
            self._repository.fetch_version_body(scope, parent_version_id),
            context,
            assets,
            products,
            target,
            direction,
            source_description,
            control,
            series_context,
            user_actuality_quotes=user_actuality_quotes,
            system_creative_plan=system_creative_plan,
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
        production_conditions = self._production_conditions(instruction, direction.media_format)
        context = self._repository.load_brand_context(target_scope, direction.media_format, production_conditions)
        self._assert_target_context(context, direction.platform)
        control = self._replayed_control(source_scope, snapshot)
        control = self._recompile_control(control)
        context = self._replayed_context(context, control, snapshot)
        series_context = frozen_series_context(snapshot)
        user_premise = frozen_user_premise(snapshot, source.weak_seed)
        user_actuality_quotes = frozen_user_actuality_quotes(snapshot)
        system_creative_plan = frozen_system_creative_plan(snapshot)
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
            user_premise,
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
                context.business_data_kind,
                context.brand_reference_context,
                user_premise,
                user_actuality_quotes,
                system_creative_plan,
            ),
            None,
        )
        return self._generate_and_persist(
            target_scope,
            target_task_id,
            run_id,
            user_premise,
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
            user_actuality_quotes=user_actuality_quotes,
            system_creative_plan=system_creative_plan,
        )

    def identity_summary(self, scope: TrustedScope, target: ContentTarget = "douyin_video") -> dict[str, str]:
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
        progress: Callable[[str], None] | None = None,
        user_actuality_quotes: tuple[str, ...] | None = None,
        system_creative_plan: str = "",
    ) -> dict[str, object]:
        try:
            # The run is already durable here. Keep the first generation event
            # inside the failure guard so a disconnected stream cannot strand
            # it in the running state.
            if progress is not None:
                progress("generating")
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
                    user_actuality_quotes=user_actuality_quotes,
                    system_creative_plan=system_creative_plan,
                )
            )
            if progress is not None:
                progress("validating")
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
        try:
            if progress is not None:
                progress("finalizing")
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
        except GenerationFailed as exc:
            self._repository.fail_run(scope, task_id, run_id, str(exc))
            raise
        except Exception as exc:
            self._repository.fail_run(scope, task_id, run_id, "成品保存失败，请稍后重试")
            raise GenerationFailed("成品保存失败，请稍后重试") from exc
        except BaseException:
            self._repository.fail_run(scope, task_id, run_id, "成品保存已取消")
            raise
        version_value = completed["version"]
        if not isinstance(version_value, int):
            raise GenerationFailed("内容版本数据无效")
        visible = self._repository.fetch_version(scope, task_id, version_value)
        creative = control.direction if control else None
        return completed | {
            "kind": "content",
            "body": visible["body"],
            "ai_generated": visible["ai_generated"],
            "aigc_label": visible["aigc_label"],
            "aigc_release_reminder": visible["aigc_release_reminder"],
            "target": visible["target"],
            "target_key": visible["target_key"],
            "adapted_from": visible["adapted_from"],
            # Shown before the artifact, never inside it, and never a review report.
            "translation_notice": creative.translation_notice if creative else None,
            "applied_direction": ([item.applied_label for item in creative.selections] if creative else []),
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
                    direction.translation_notice if any(item.translated for item in selections) else None
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
        if re.search(
            r"(?:一个人|一人)(?:完成|制作|拍|录|剪)|(?:用|只用|只有|一部)手机(?:拍|录|制作|完成)?",
            text,
        ):
            return (
                "只使用用户本次明确点名的单人或手机制作条件；"
                "未点名的人物、物品、场地和既有素材仍视为不可用。"
            )
        if previous is not None:
            return previous
        return (
            f"按当前{media_format}形式自主选择表现方式；"
            "可使用创作者本人表达与本次原创的抽象构图、排版、文字和声音组织，"
            "不默认任何现实人物、商品、物品、场地或既有素材存在。"
        )

    @staticmethod
    def _requests_independent_result(text: str) -> bool:
        return any(marker in text for marker in ("另外", "独立", "单独拍", "单独用", "另一条"))

    @staticmethod
    def _assert_target_context(context: BrandContext, platform: str) -> None:
        if context.platform != platform:
            raise DomainError("当前可信内容身份不能使用该目标平台")
