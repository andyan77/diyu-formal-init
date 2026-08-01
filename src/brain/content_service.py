from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace
from typing import cast
from uuid import UUID

from src.brain.content_control_service import (
    PREFERENCE_ABSENT,
    PREFERENCE_BYPASSED,
    ContentControlService,
)
from src.brain.content_expression import direction_from_snapshot, snapshot_document
from src.brain.creation_intent_gate import (
    CreationCommitment,
    evaluate_creation_intent,
    requires_indispensable_user_fact,
)
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
from src.shared.content_origin import aigc_disclosure, is_ai_generated_content
from src.shared.content_snapshot import (
    frozen_creative_kernel,
    frozen_creative_plan,
    frozen_delivery_compiler_version,
    frozen_media_contract,
    frozen_narrative_frame,
    frozen_product_value_contract,
    frozen_series_context,
    frozen_user_premise,
)
from src.shared.creative_kernel import CreativeKernelV1
from src.shared.creative_plan import (
    ACCOUNT_BASELINE_TONE_ID,
    CreativePlanV2,
    build_creative_plan,
    platform_shape,
    validate_creative_plan,
)
from src.shared.delivery_compiler import (
    DELIVERY_COMPILER_VERSION,
    SUPPORTED_DELIVERY_COMPILER_VERSIONS,
)
from src.shared.errors import DomainError, GenerationFailed
from src.shared.factual_basis import brand_fact_records, product_fact_records
from src.shared.media_program import (
    BoundProductMediaResourceV2,
    MediaCapabilityEnvelope,
    MediaProgramSelectionV1,
    build_media_capability_envelope_v2,
    retarget_media_envelope,
    select_media_program,
)
from src.shared.narrative import (
    NarrativeFrame,
    NarrativeMode,
    legacy_frame,
    new_frame,
    user_fact_candidates,
    visible_digest,
)
from src.shared.product_value import (
    ProductValueContract,
    build_product_value_contract,
)
from src.shared.service_status import ProviderStatusTracker
from src.shared.types import (
    AccountExpression,
    ActiveAsset,
    BrandContext,
    BrandContextPacketV1,
    BrandContextSegment,
    ContentControlContext,
    ContentProduct,
    ContentTarget,
    ConversationDecision,
    ConversationInput,
    ConversationTurn,
    GenerationInput,
    MediaFormat,
    PlatformDirection,
    ProductFact,
    ReferenceMaterial,
    RequestedControls,
    RoutingInput,
    SeriesContext,
    SpeakerKind,
    TrustedScope,
)

_NO_FROZEN_CONTEXT = "这条历史内容没有保留完整的创作条件，请按当前输入新建一条。"
_MISSING_FROZEN_MATERIAL = "这条内容当时用到的参考素材已经不可用，请按当前输入新建一条。"
_MISSING_FROZEN_PROFILE = "这条内容当时用到的账号表达画像已经读不到了，请按当前输入新建一条。"
_EXPLICIT_DRAMATIZATION_CONTROL = re.compile(
    r"(?:写|做|创作|生成|改编|整理)(?:成|为)?"
    r"[^，,。！？!?\n]{0,48}?"
    r"(?:情境演绎|情景演绎|情景剧|短剧|小剧场)"
)
_NEGATED_CONTROL_SUFFIXES = ("不要", "别", "不想", "不用", "无需", "避免")
_TARGET_LABELS: dict[ContentTarget, str] = {
    "douyin_video": "抖音视频",
    "xiaohongshu_video": "小红书视频",
    "xiaohongshu_graphic": "小红书图文",
    "wechat_channels_video": "微信视频号视频",
}


def _requests_explicit_dramatization(natural_text: str) -> bool:
    for match in _EXPLICIT_DRAMATIZATION_CONTROL.finditer(natural_text):
        prefix = natural_text[max(0, match.start() - 4) : match.start()]
        if not prefix.endswith(_NEGATED_CONTROL_SUFFIXES):
            return True
    return False


class ContentService:
    def __init__(
        self,
        repository: ContentRepository,
        generator: ContentGenerator,
        control_service: ContentControlService | None = None,
        provider_status: ProviderStatusTracker | None = None,
    ) -> None:
        self._repository = repository
        self._generator = generator
        self._control = control_service
        self.provider_status = provider_status or ProviderStatusTracker()

    def completed_request(
        self,
        scope: TrustedScope,
        client_request_id: UUID,
    ) -> dict[str, object] | None:
        """Read a previously committed response before reserving provider capacity."""
        return self._repository.completed_request(scope, client_request_id)

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
        narrative_frame: NarrativeFrame | None = None,
        creative_plan: CreativePlanV2 | None = None,
        creation_commitment: CreationCommitment | None = None,
        explicit_ui: bool = True,
        client_request_id: UUID | None = None,
    ) -> dict[str, object]:
        if client_request_id is not None:
            completed = self._repository.completed_request(scope, client_request_id)
            if completed is not None:
                return completed
        if (
            creation_commitment is None
            and primary_product_override is None
            and reuse_version_id is None
            and is_natural_chat(weak_seed)
        ):
            return {"kind": "greeting", "message": natural_reply()}
        commitment = creation_commitment or evaluate_creation_intent(
            (weak_seed,),
            explicit_ui=explicit_ui,
            creation_kind=(
                "continuation" if reuse_version_id is not None or requests_continuation(weak_seed) else "new_content"
            ),
        )
        if not commitment.committed:
            return {"kind": "greeting", "message": natural_reply()}
        if series_position is not None and series_id is None:
            raise DomainError("指定系列集数前，请先选择一个系列。")
        continuation = reuse_version_id is None and series_id is None and requests_continuation(weak_seed)
        if continuation:
            reuse_version_id = self._repository.latest_visible_version(scope)
            if reuse_version_id is None:
                return {"kind": "greeting", "message": "还没有当前账号可继续的上一条内容。"}
        sanitized_seed = sanitize_seed(weak_seed)
        direction = direction_for(target)
        production_conditions = self._production_conditions(sanitized_seed, direction.media_format)
        context = self._repository.load_brand_context(scope, direction.media_format, production_conditions)
        self._assert_target_context(context, direction.platform)
        control = self._control_context(
            scope,
            context,
            controls,
            sanitized_seed,
        )
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
            named_products = self._repository.load_product_facts(
                scope,
                sanitized_seed,
            )
            bound_products = self._bound_products(control)
            products = named_products
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
            if primary_product == "visual_styling_story":
                if not bound_products:
                    return {
                        "kind": "question",
                        "message": self._product_media_selection_question(),
                    }
                named_skus = {product.sku for product in named_products}
                bound_skus = {product.sku for product in bound_products}
                if named_skus and not named_skus <= bound_skus:
                    return {
                        "kind": "question",
                        "message": ("你提到的商品与本次选择的登记素材不一致，请保留对应素材或重新选择商品。"),
                    }
                products = bound_products
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
            return {
                "kind": "question",
                "message": self._product_media_selection_question(),
            }
        context = self._repository.select_brand_context_for_task(
            scope,
            context,
            sanitized_seed,
            primary_product,
            products,
        )
        assets = self._repository.load_active_assets(
            scope, primary_product, sanitized_seed, products, target, is_recompile
        )
        plan = creative_plan or self._default_creative_plan(
            sanitized_seed,
            primary_product,
            control,
            target,
            direction.media_format,
        )
        self._validate_plan(
            plan,
            (sanitized_seed,),
            primary_product,
            control,
            target,
            direction.media_format,
        )
        frozen_frame = self._frame_with_brand_facts(
            narrative_frame,
            products,
            context,
        )
        try:
            media_envelope, media_program = self._new_media_contract(
                control=control,
                target=target,
                media_format=direction.media_format,
                primary_product=primary_product,
                creative_plan=plan,
                series_context=series_context,
                fact_count=len(frozen_frame.allowed_fact_ids),
            )
            product_value_contract = build_product_value_contract(
                primary_product=primary_product,
                products=products,
                bound_product_media=control.bound_product_media,
                media_envelope=media_envelope,
                media_program=media_program,
            )
        except GenerationFailed as exc:
            return {"kind": "question", "message": str(exc)}
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
                frozen_frame,
                sanitized_seed,
                plan,
                commitment,
                media_capability_envelope=media_envelope,
                media_program=media_program,
                product_value_contract=product_value_contract,
                brand_context_packet=context.context_packet,
            ),
            series_context,
            client_request_id=client_request_id,
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
            frozen_frame,
            plan,
            DELIVERY_COMPILER_VERSION,
            None,
            media_envelope,
            media_program,
            product_value_contract,
        )

    @staticmethod
    def _frame_with_brand_facts(
        frame: NarrativeFrame | None,
        products: tuple[ProductFact, ...],
        context: BrandContext,
    ) -> NarrativeFrame:
        product_ids = tuple(record.fact_id for product in products for record in product_fact_records(product))
        brand_ids = tuple(record.fact_id for record in brand_fact_records(context.brand_reference_context))
        if frame is None:
            return new_frame("general_observation", (), product_ids, brand_ids)
        return new_frame(
            frame.narrative_mode,
            tuple(fact.exact_text for fact in frame.user_facts),
            product_ids,
            brand_ids,
            user_fact_source_ids=tuple(fact.source_id for fact in frame.user_facts),
        )

    @staticmethod
    def _bound_products(
        control: ContentControlContext,
    ) -> tuple[ProductFact, ...]:
        products: dict[UUID, ProductFact] = {}
        for item in control.bound_product_media:
            products.setdefault(item.product_id, item.product)
        return tuple(products.values())

    @staticmethod
    def _requests_visual_product_story(
        control: ContentControlContext,
        controls: RequestedControls | None,
    ) -> bool:
        """Separate an explicit P5 route request from trusted media capability."""
        return bool(controls and controls.product_media_intent) or (
            ContentService._has_complete_product_media_pair(control, controls)
        )

    @staticmethod
    def _has_complete_product_media_pair(
        control: ContentControlContext,
        controls: RequestedControls | None,
    ) -> bool:
        requested_ids = () if controls is None else controls.material_ids
        records = control.bound_product_media
        return (
            len(requested_ids) == 2
            and len(set(requested_ids)) == 2
            and len(records) == 2
            and {record.asset_id for record in records} == set(requested_ids)
            and len({record.product_id for record in records}) == 2
            and len({record.binding_id for record in records}) == 2
        )

    @staticmethod
    def _product_media_selection_question() -> str:
        return "当前可用于制作的登记商品素材不足。这条视觉内容需要选择两件不同商品，并为每件选择一份已登记图片。"

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
        direct_generate: bool = False,
        conversation_only: bool = False,
        client_request_id: UUID | None = None,
    ) -> dict[str, object]:
        """Collaborate without persistence until one request is genuinely generation-ready."""
        if not conversation_only and client_request_id is not None:
            completed = self._repository.completed_request(scope, client_request_id)
            if completed is not None:
                return completed
        raw_history = tuple(history[-8:])
        if raw_history and raw_history[-1].role == "user" and raw_history[-1].content == message:
            raw_history = raw_history[:-1]
        raw_user_turns = tuple(turn.content for turn in raw_history if turn.role == "user") + (message,)
        commitment = evaluate_creation_intent(
            () if conversation_only else raw_user_turns,
            explicit_ui=direct_generate and not conversation_only,
        )
        sanitized_message = sanitize_seed(message)
        sanitized_history = tuple(ConversationTurn(turn.role, sanitize_seed(turn.content)) for turn in raw_history)
        if (
            sanitized_history
            and sanitized_history[-1].role == "user"
            and sanitized_history[-1].content == sanitized_message
        ):
            sanitized_history = sanitized_history[:-1]
        if not commitment.committed and not sanitized_history and is_natural_chat(sanitized_message):
            return {"kind": "chat", "message": natural_reply()}
        if commitment.committed and progress is not None:
            progress("received")
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
        control = self._control_context(scope, context, controls, combined_text)
        products = self._repository.load_product_facts(
            scope,
            combined_text,
        )
        visual_product_requested = self._requests_visual_product_story(
            control,
            controls,
        )
        if visual_product_requested:
            if not self._has_complete_product_media_pair(control, controls):
                return {
                    "kind": "question",
                    "message": self._product_media_selection_question(),
                }
            bound_products = self._bound_products(control)
            named_skus = {product.sku for product in products}
            bound_skus = {product.sku for product in bound_products}
            if named_skus and not named_skus <= bound_skus:
                return {
                    "kind": "question",
                    "message": "你提到的商品与本次选择的登记素材不一致，请保留对应素材或重新选择商品。",
                }
            products = bound_products
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
        available_user_turns = tuple(turn.content for turn in sanitized_history if turn.role == "user") + (
            sanitized_message,
        )
        fact_candidates = user_fact_candidates(available_user_turns)
        decision: ConversationDecision = self._generator.collaborate(
            ConversationInput(
                message=sanitized_message,
                history=sanitized_history,
                brand=context,
                products=products,
                target=target,
                selected_direction=selected_direction,
                explicit_narrative_mode=self._explicit_narrative_mode(
                    control,
                    sanitized_message,
                ),
                prior_series_summary=series_summary,
                creation_committed=commitment.committed,
                indispensable_fact_question_allowed=(
                    commitment.committed
                    and requires_indispensable_user_fact(commitment.intent_span)
                ),
                allowed_tone_ids=self._allowed_tone_ids(control),
                allowed_mechanism_ids=self._allowed_mechanism_ids(control),
                platform_shape=platform_shape(target, direction.media_format),
                user_fact_candidates=fact_candidates,
            )
        )
        if not commitment.committed:
            return {
                "kind": "chat",
                "message": (decision.message if decision.disposition == "chat" else natural_reply()),
                "direct_generation_available": bool(decision.creation_proposal or decision.disposition == "ready"),
            }
        if decision.disposition != "ready":
            return {
                "kind": decision.disposition,
                "message": decision.message,
            }
        if (
            not decision.user_fact_source_ids
            and not products
            and requires_indispensable_user_fact(commitment.intent_span)
        ):
            return {
                "kind": "question",
                "message": "这段真实经历里，哪一件具体发生的事是必须保留的？",
            }
        if (
            decision.primary_product is None
            or decision.narrative_mode is None
            or not decision.user_premises
            or decision.creative_plan is None
        ):
            raise GenerationFailed("这次还没能整理成可靠的创作要求，请继续补充一句。")
        primary_product = decision.primary_product
        narrative_mode = decision.narrative_mode
        creative_plan = decision.creative_plan
        if visual_product_requested:
            primary_product = "visual_styling_story"
            creative_plan = replace(
                creative_plan,
                primary_value="visual_styling_story",
            )
        if primary_product == "visual_styling_story":
            bound_products = self._bound_products(control)
            if not bound_products:
                return {
                    "kind": "question",
                    "message": self._product_media_selection_question(),
                }
            products = bound_products
        if sanitized_message not in decision.user_premises or any(
            premise not in available_user_turns for premise in decision.user_premises
        ):
            raise GenerationFailed("模型没有可靠保留用户原话")
        candidate_by_id = {candidate.source_id: candidate.exact_text for candidate in fact_candidates}
        if len(decision.user_fact_source_ids) != len(decision.user_fact_spans) or any(
            candidate_by_id.get(source_id) != exact_text
            for source_id, exact_text in zip(
                decision.user_fact_source_ids,
                decision.user_fact_spans,
                strict=True,
            )
        ):
            raise GenerationFailed("模型返回的用户事实句标识不存在或原文漂移")
        premise = "\n".join(decision.user_premises)
        self._validate_plan(
            creative_plan,
            available_user_turns,
            primary_product,
            control,
            target,
            direction.media_format,
        )
        frame = new_frame(
            narrative_mode,
            decision.user_fact_spans,
            tuple(record.fact_id for product in products for record in product_fact_records(product)),
            (),
            user_fact_source_ids=decision.user_fact_source_ids,
        )
        explicit_mode = self._explicit_narrative_mode(control, sanitized_message)
        if explicit_mode is not None and frame.narrative_mode != explicit_mode:
            raise GenerationFailed("叙事模式与用户显式形式选择不一致")
        result = self.create_from_weak_seed(
            scope,
            premise,
            target=target,
            controls=controls,
            series_id=series_id,
            series_position=series_position,
            primary_product_override=primary_product,
            progress=progress,
            narrative_frame=frame,
            creative_plan=creative_plan,
            creation_commitment=commitment,
            client_request_id=client_request_id,
        )
        return result | {"conversation_message": decision.message}

    @staticmethod
    def _explicit_narrative_mode(
        control: ContentControlContext,
        natural_text: str = "",
    ) -> NarrativeMode | None:
        if natural_text.lstrip().startswith(("如果", "假如", "假设")):
            return "hypothesis"
        if _requests_explicit_dramatization(natural_text):
            return "dramatization"
        if control.direction is None:
            return None
        if any(
            item.axis == "mechanism" and item.stable_id == "CAT-GENRE-DRAMA-04" and item.origin == "explicit"
            for item in control.direction.selections
        ):
            return "dramatization"
        return None

    @staticmethod
    def _allowed_tone_ids(
        control: ContentControlContext,
    ) -> tuple[str, ...]:
        selected = (
            tuple(item.stable_id for item in control.direction.selections if item.axis == "style")
            if control.direction is not None
            else ()
        )
        return tuple(dict.fromkeys((ACCOUNT_BASELINE_TONE_ID, *selected)))

    @staticmethod
    def _allowed_mechanism_ids(
        control: ContentControlContext,
    ) -> tuple[str, ...]:
        return (
            tuple(item.stable_id for item in control.direction.selections if item.axis == "mechanism")
            if control.direction is not None
            else ()
        )

    @classmethod
    def _default_creative_plan(
        cls,
        premise: str,
        primary_product: ContentProduct,
        control: ContentControlContext,
        target: ContentTarget,
        media_format: str,
    ) -> CreativePlanV2:
        tone_ids = cls._allowed_tone_ids(control)
        mechanisms = cls._allowed_mechanism_ids(control)
        selected_styles = tuple(identifier for identifier in tone_ids if identifier != ACCOUNT_BASELINE_TONE_ID)
        return build_creative_plan(
            topic_spans=(premise,),
            primary_value=primary_product,
            tone_ids=selected_styles or (ACCOUNT_BASELINE_TONE_ID,),
            mechanism_id=mechanisms[0] if mechanisms else None,
            target_shape=platform_shape(target, media_format),
        )

    @classmethod
    def _validate_plan(
        cls,
        plan: CreativePlanV2,
        user_turns: tuple[str, ...],
        primary_product: ContentProduct,
        control: ContentControlContext,
        target: ContentTarget,
        media_format: str,
    ) -> None:
        validate_creative_plan(
            plan,
            user_turns=user_turns,
            allowed_tone_ids=cls._allowed_tone_ids(control),
            allowed_mechanism_ids=cls._allowed_mechanism_ids(control),
            expected_primary_value=primary_product,
            expected_platform_shape=platform_shape(target, media_format),
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
                speaker_kind=context.speaker_kind,
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
            bound_product_media=self._control.bound_product_media(
                scope,
                requested.material_ids,
            ),
            content_role=context.content_role_name,
            content_role_boundary=context.content_role_boundary,
            speaker_kind=context.speaker_kind,
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
        material_snapshots = snapshot.get("material_snapshots")
        if isinstance(material_snapshots, list):
            frozen_materials: list[ReferenceMaterial] = []
            for item in material_snapshots:
                if not isinstance(item, dict) or not item.get("asset_id"):
                    raise DomainError(_MISSING_FROZEN_MATERIAL)
                raw_version = item.get("reference_version")
                if not isinstance(raw_version, int):
                    raise DomainError(_MISSING_FROZEN_MATERIAL)
                frozen_materials.append(
                    ReferenceMaterial(
                        asset_id=UUID(str(item["asset_id"])),
                        title=str(item.get("title") or ""),
                        media_type=str(item.get("media_type") or ""),
                        reference_version=raw_version,
                        text_body=str(item.get("text_body") or ""),
                        reference_note=str(item.get("reference_note") or ""),
                    )
                )
            materials = tuple(frozen_materials)
        elif self._control is not None and frozen_versions:
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
        frozen_speaker_kind = snapshot.get("speaker_kind")
        return ContentControlContext(
            catalog_version=str(catalog_version) if isinstance(catalog_version, str) else None,
            direction=direction_from_snapshot(snapshot),
            account_expression=expression,
            materials=materials,
            preference_mode=str(snapshot.get("private_preference_mode") or PREFERENCE_ABSENT),
            preference_version=(preference_version if isinstance(preference_version, int) else None),
            content_role=str(frozen_role) if isinstance(frozen_role, str) else "",
            content_role_boundary=(str(frozen_boundary) if isinstance(frozen_boundary, str) else ""),
            speaker_kind=cast(
                SpeakerKind,
                (
                    frozen_speaker_kind
                    if frozen_speaker_kind
                    in {
                        "institutional_account",
                        "personal_ip_account",
                        "unknown",
                    }
                    else "unknown"
                ),
            ),
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
        frozen_packet = ContentService._brand_context_packet_from_snapshot(snapshot)
        frozen_constraints = (
            tuple(
                segment.exact_text
                for segment in frozen_packet.segments
                if segment.semantic_kind == "expression_constraint"
            )
            if frozen_packet is not None
            else context.expression_constraint_context
        )
        frozen_methods = (
            tuple(
                segment.exact_text for segment in frozen_packet.segments if segment.semantic_kind == "creative_method"
            )
            if frozen_packet is not None
            else context.creative_method_context
        )
        frozen_product_guidance = (
            tuple(
                segment.exact_text
                for segment in frozen_packet.segments
                if segment.semantic_kind == "candidate_product_guidance"
            )
            if frozen_packet is not None
            else context.candidate_product_guidance_context
        )
        if not control.content_role:
            return replace(
                context,
                brand_reference_context=frozen_references,
                expression_constraint_context=frozen_constraints,
                creative_method_context=frozen_methods,
                candidate_product_guidance_context=frozen_product_guidance,
                context_packet=frozen_packet,
            )
        return replace(
            context,
            content_role_name=control.content_role,
            content_role_boundary=control.content_role_boundary or context.content_role_boundary,
            brand_reference_context=frozen_references,
            expression_constraint_context=frozen_constraints,
            creative_method_context=frozen_methods,
            candidate_product_guidance_context=frozen_product_guidance,
            context_packet=frozen_packet,
            speaker_kind=control.speaker_kind,
        )

    @staticmethod
    def _brand_context_packet_from_snapshot(
        snapshot: dict[str, object] | None,
    ) -> BrandContextPacketV1 | None:
        if snapshot is None:
            return None
        raw = snapshot.get("brand_context_packet")
        if not isinstance(raw, dict) or raw.get("packet_version") != "brand-context-packet-v1":
            return None
        raw_segments = raw.get("segments")
        if not isinstance(raw_segments, list):
            raise DomainError("内容任务冻结的品牌资料包无效")
        segments: list[BrandContextSegment] = []
        for item in raw_segments:
            if not isinstance(item, dict):
                raise DomainError("内容任务冻结的品牌资料包无效")
            required = (
                "segment_id",
                "source_document_id",
                "source_document_version_id",
                "source_id",
                "source_version",
                "semantic_kind",
                "evidence_level",
                "visibility_scope",
                "digest",
                "exact_text",
            )
            if any(not isinstance(item.get(key), str) for key in required):
                raise DomainError("内容任务冻结的品牌资料包无效")
            segments.append(BrandContextSegment(**{key: str(item[key]) for key in required}))
        digest = raw.get("packet_digest")
        if not isinstance(digest, str):
            raise DomainError("内容任务冻结的品牌资料包无效")
        return BrandContextPacketV1("brand-context-packet-v1", digest, tuple(segments))

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
        client_request_id: UUID | None = None,
    ) -> dict[str, object]:
        if client_request_id is not None:
            completed = self._repository.completed_request(scope, client_request_id)
            if completed is not None:
                return completed
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
        frame = frozen_narrative_frame(snapshot)
        weak_seed = frozen_user_premise(snapshot, weak_seed)
        context = self._replayed_context(context, control, snapshot)
        creative_plan = frozen_creative_plan(snapshot)
        delivery_compiler_version = frozen_delivery_compiler_version(snapshot)
        prior_creative_kernel = frozen_creative_kernel(snapshot)
        media_envelope, media_program = frozen_media_contract(snapshot)
        product_value_contract = frozen_product_value_contract(snapshot)
        if delivery_compiler_version is not None and (
            delivery_compiler_version not in SUPPORTED_DELIVERY_COMPILER_VERSIONS or prior_creative_kernel is None
        ):
            raise GenerationFailed("这条内容冻结的创作内核无法可靠读取")
        if delivery_compiler_version == DELIVERY_COMPILER_VERSION and (media_envelope is None or media_program is None):
            raise GenerationFailed("这条内容冻结的媒体合同无法可靠读取")
        if creative_plan is None:
            frame = new_frame(
                (frame.narrative_mode if frame is not None else "general_observation"),
                (tuple(fact.exact_text for fact in frame.user_facts) if frame is not None else ()),
                tuple(record.fact_id for product in products for record in product_fact_records(product)),
                tuple(record.fact_id for record in brand_fact_records(context.brand_reference_context)),
            )
            creative_plan = self._default_creative_plan(
                weak_seed,
                primary_product,
                control,
                target,
                media_format,
            )
        elif frame is None:
            frame = legacy_frame(
                tuple(record.fact_id for product in products for record in product_fact_records(product))
            )
        if delivery_compiler_version is None:
            delivery_compiler_version = DELIVERY_COMPILER_VERSION
        self._validate_plan(
            creative_plan,
            (weak_seed,),
            primary_product,
            control,
            target,
            media_format,
        )
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
            client_request_id=client_request_id,
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
            source_description,
            control,
            series_context,
            None,
            frame,
            creative_plan,
            delivery_compiler_version,
            prior_creative_kernel,
            media_envelope,
            media_program,
            product_value_contract,
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
        frame = frozen_narrative_frame(snapshot)
        source_premise = frozen_user_premise(snapshot, source.weak_seed)
        creative_plan = frozen_creative_plan(snapshot)
        delivery_compiler_version = frozen_delivery_compiler_version(snapshot)
        prior_creative_kernel = frozen_creative_kernel(snapshot)
        source_media_envelope, _ = frozen_media_contract(snapshot)
        product_value_contract = frozen_product_value_contract(snapshot)
        if delivery_compiler_version is not None and (
            delivery_compiler_version not in SUPPORTED_DELIVERY_COMPILER_VERSIONS or prior_creative_kernel is None
        ):
            raise GenerationFailed("源内容冻结的创作内核无法可靠读取")
        if creative_plan is None:
            frame = new_frame(
                (frame.narrative_mode if frame is not None else "general_observation"),
                (tuple(fact.exact_text for fact in frame.user_facts) if frame is not None else ()),
                tuple(record.fact_id for product in source.products for record in product_fact_records(product)),
                tuple(record.fact_id for record in brand_fact_records(context.brand_reference_context)),
            )
            creative_plan = self._default_creative_plan(
                source_premise,
                source.primary_product,
                control,
                target,
                direction.media_format,
            )
        else:
            allowed_tones = self._allowed_tone_ids(control)
            selected_tones = tuple(identifier for identifier in allowed_tones if identifier != ACCOUNT_BASELINE_TONE_ID)
            allowed_mechanisms = self._allowed_mechanism_ids(control)
            creative_plan = build_creative_plan(
                topic_spans=creative_plan.topic_spans,
                primary_value=creative_plan.primary_value,
                tone_ids=selected_tones or (ACCOUNT_BASELINE_TONE_ID,),
                mechanism_id=(
                    creative_plan.mechanism_id
                    if creative_plan.mechanism_id in allowed_mechanisms
                    else (allowed_mechanisms[0] if allowed_mechanisms else None)
                ),
                target_shape=platform_shape(target, direction.media_format),
            )
            if frame is None:
                frame = legacy_frame(
                    tuple(record.fact_id for product in source.products for record in product_fact_records(product))
                )
        if delivery_compiler_version is None:
            delivery_compiler_version = DELIVERY_COMPILER_VERSION
        self._validate_plan(
            creative_plan,
            (source_premise,),
            source.primary_product,
            control,
            target,
            direction.media_format,
        )
        media_envelope: MediaCapabilityEnvelope | None = None
        media_program: MediaProgramSelectionV1 | None = None
        if delivery_compiler_version == DELIVERY_COMPILER_VERSION:
            try:
                frozen_product_resources = (
                    tuple(
                        resource
                        for resource in source_media_envelope.resources
                        if isinstance(
                            resource,
                            BoundProductMediaResourceV2,
                        )
                    )
                    if source_media_envelope is not None
                    else ()
                )
                if frozen_product_resources:
                    if source_media_envelope is None:
                        raise GenerationFailed("源内容缺少冻结的媒体能力合同")
                    if self._control is None:
                        raise GenerationFailed("当前无法核对源内容的冻结商品素材")
                    root_id, control_organization_id = self._control.account_media_scope(
                        target_scope,
                    )
                    if any(
                        resource.root_account_id != str(root_id)
                        or resource.control_organization_id != str(control_organization_id)
                        for resource in frozen_product_resources
                    ):
                        raise GenerationFailed("目标发布账号不能使用源内容冻结的商品素材")
                    media_envelope = retarget_media_envelope(
                        source_media_envelope,
                        platform_shape=platform_shape(
                            target,
                            direction.media_format,
                        ),
                        media_format=direction.media_format,
                    )
                    media_program = select_media_program(
                        primary_product=source.primary_product,
                        envelope=media_envelope,
                        mechanism_id=creative_plan.mechanism_id,
                        series_position=(series_context.target_position if series_context is not None else None),
                        fact_count=(len(frame.allowed_fact_ids) if frame is not None else 0),
                    )
                else:
                    media_envelope, media_program = self._new_media_contract(
                        control=control,
                        target=target,
                        media_format=direction.media_format,
                        primary_product=source.primary_product,
                        creative_plan=creative_plan,
                        series_context=series_context,
                        fact_count=(len(frame.allowed_fact_ids) if frame is not None else 0),
                    )
            except GenerationFailed as exc:
                return {"kind": "question", "message": str(exc)}
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
            source_premise,
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
                frame,
                source_premise,
                creative_plan,
                evaluate_creation_intent(
                    (instruction,),
                    active_revision=True,
                    creation_kind="recompile",
                ),
                delivery_compiler_version=delivery_compiler_version,
                media_capability_envelope=media_envelope,
                media_program=media_program,
                product_value_contract=product_value_contract,
                brand_context_packet=context.context_packet,
            ),
            None,
        )
        return self._generate_and_persist(
            target_scope,
            target_task_id,
            run_id,
            source_premise,
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
            None,
            frame,
            creative_plan,
            delivery_compiler_version,
            prior_creative_kernel,
            media_envelope,
            media_program,
            product_value_contract,
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

    @staticmethod
    def _new_media_contract(
        *,
        control: ContentControlContext,
        target: ContentTarget,
        media_format: str,
        primary_product: ContentProduct,
        creative_plan: CreativePlanV2,
        series_context: SeriesContext | None,
        fact_count: int,
    ) -> tuple[MediaCapabilityEnvelope, MediaProgramSelectionV1]:
        if media_format not in {"graphic", "video"}:
            raise GenerationFailed("当前内容形式没有可用的媒体程序")
        envelope = build_media_capability_envelope_v2(
            platform_shape=platform_shape(
                target,
                cast(MediaFormat, media_format),
            ),
            media_format=cast(MediaFormat, media_format),
            selected_materials=control.materials,
            bound_product_media=control.bound_product_media,
        )
        program = select_media_program(
            primary_product=primary_product,
            envelope=envelope,
            mechanism_id=creative_plan.mechanism_id,
            series_position=(series_context.target_position if series_context is not None else None),
            fact_count=fact_count,
        )
        return envelope, program

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
        narrative_frame: NarrativeFrame | None = None,
        creative_plan: CreativePlanV2 | None = None,
        delivery_compiler_version: str | None = None,
        prior_creative_kernel: CreativeKernelV1 | None = None,
        media_capability_envelope: MediaCapabilityEnvelope | None = None,
        media_program: MediaProgramSelectionV1 | None = None,
        product_value_contract: ProductValueContract | None = None,
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
                    narrative_frame=narrative_frame,
                    creative_plan=creative_plan,
                    delivery_compiler_version=delivery_compiler_version,
                    prior_creative_kernel=prior_creative_kernel,
                    media_capability_envelope=media_capability_envelope,
                    media_program=media_program,
                    product_value_contract=product_value_contract,
                )
            )
            if progress is not None:
                progress("validating")
            if narrative_frame is not None and artifact.reviewed_digest != visible_digest(
                artifact.outline, artifact.body
            ):
                raise GenerationFailed("最终成品与被审查内容不一致")
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
                snapshot_patch=artifact.completion_snapshot_patch,
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
        visible_body = completed.get("body")
        visible_outline = completed.get("outline")
        if not isinstance(visible_body, str) or not isinstance(
            visible_outline,
            str,
        ):
            raise GenerationFailed("内容版本提交回读数据无效")
        aigc_label, aigc_release_reminder = aigc_disclosure(artifact.model)
        creative = control.direction if control else None
        material_categories = {
            "brand_fact": "品牌已确认资料",
            "expression_constraint": "品牌表达边界",
            "creative_method": "品牌创作方法",
            "candidate_product_guidance": "候选商品参考",
            "source_catalog_only": "来源目录",
        }
        packet_segments = context.context_packet.segments if context.context_packet is not None else ()
        context_basis = {
            "account": context.account_name,
            "platform_and_format": f"{context.platform} · {context.media_format}",
            "brand_material_categories": list(
                dict.fromkeys(material_categories.get(segment.semantic_kind, "品牌资料") for segment in packet_segments)
            ),
            "has_product_facts": bool(products),
            "selected_material_count": len(control.materials) if control else 0,
            "gaps": [
                label
                for missing, label in (
                    (not products, "本次没有使用具体商品资料"),
                    (not (control and control.materials), "本次没有选择制作素材"),
                )
                if missing
            ],
        }
        return completed | {
            "kind": "content",
            "outline": visible_outline,
            "body": visible_body,
            "ai_generated": is_ai_generated_content(artifact.model),
            "aigc_label": aigc_label,
            "aigc_release_reminder": aigc_release_reminder,
            "target": _TARGET_LABELS[target],
            "target_key": target,
            "adapted_from": source_version_description,
            # Shown before the artifact, never inside it, and never a review report.
            "translation_notice": creative.translation_notice if creative else None,
            "applied_direction": ([item.applied_label for item in creative.selections] if creative else []),
            "context_basis": context_basis,
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
        if any(marker in text for marker in ("无口播", "无对白", "无解说")):
            return "本次采用无口播、无对白、无解说的视频表达；完整已审文字使用文字卡或字幕呈现，不要求现实环境声。"
        if "8 秒" in text or "8秒" in text:
            return "目标自然时长为 8 秒；无法同时保留原有全部认知时，只做明确标识的窄主题版，不称与原版等义。"
        if "四张" in text or "4 张" in text or "4张" in text:
            return "当前只补拍四张；图文仍须有完整正文，并由正文保留商品归因边界。"
        if "一个人" in text or "一人" in text or "手机" in text:
            return (
                "只登记创作者本人表达与本次原创抽象构成为通用能力；用户明确点名的一人或手机"
                "要求只约束本次制作，不证明任何现实人物、场地、道具或素材存在。"
            )
        if previous is not None:
            return previous
        del media_format
        return (
            "系统按内容形式自主选择创作者本人表达或本次原创抽象构图、排版、文字与声音组织；"
            "不默认任何现实人物、商品、物品、场地或既有素材可用。"
        )

    @staticmethod
    def _requests_independent_result(text: str) -> bool:
        return any(marker in text for marker in ("另外", "独立", "单独拍", "单独用", "另一条"))

    @staticmethod
    def _assert_target_context(context: BrandContext, platform: str) -> None:
        if context.platform != platform:
            raise DomainError("当前可信内容身份不能使用该目标平台")
