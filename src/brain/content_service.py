from __future__ import annotations

from uuid import UUID

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
from src.shared.errors import DomainError, GenerationFailed
from src.shared.types import (
    ActiveAsset,
    BrandContext,
    ContentProduct,
    ContentTarget,
    GenerationInput,
    PlatformDirection,
    ProductFact,
    RoutingInput,
    TrustedScope,
)


class ContentService:
    def __init__(self, repository: ContentRepository, generator: ContentGenerator) -> None:
        self._repository = repository
        self._generator = generator

    def create_from_weak_seed(
        self,
        scope: TrustedScope,
        weak_seed: str,
        reuse_version_id: UUID | None = None,
        target: ContentTarget = "douyin_video",
    ) -> dict[str, object]:
        if reuse_version_id is None and is_natural_chat(weak_seed):
            return {"kind": "greeting", "message": natural_reply()}
        continuation = reuse_version_id is None and requests_continuation(weak_seed)
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
            primary_product = self._generator.route(RoutingInput(sanitized_seed, context, products))
            prior_body = None
            source_description = None
        if primary_product is None:
            return {"kind": "greeting", "message": natural_reply()}
        if primary_product == "visual_styling_story" and not products:
            return {"kind": "question", "message": "这条视觉内容要以哪件当前品牌商品为锚？"}
        assets = self._repository.load_active_assets(
            scope, primary_product, sanitized_seed, products, target, is_recompile
        )
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
        )

    def revise(
        self,
        scope: TrustedScope,
        task_id: UUID,
        instruction: str,
        target: ContentTarget = "douyin_video",
    ) -> dict[str, object]:
        direction = direction_for(target)
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
    ) -> dict[str, object]:
        source_version_id = self._repository.latest_task_version(source_scope, task_id)
        return self.create_from_weak_seed(target_scope, instruction, source_version_id, target)

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
                )
            )
            assert_content_complete(artifact)
        except GenerationFailed as exc:
            self._repository.fail_run(scope, task_id, run_id, str(exc))
            raise
        except Exception as exc:  # Provider implementation details never reach the user.
            self._repository.fail_run(scope, task_id, run_id, "模型调用失败，请稍后重试")
            raise GenerationFailed("模型调用失败，请稍后重试") from exc
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
        return completed | {
            "kind": "content",
            "ai_generated": visible["ai_generated"],
            "aigc_label": visible["aigc_label"],
            "aigc_release_reminder": visible["aigc_release_reminder"],
            "target": visible["target"],
            "target_key": visible["target_key"],
            "adapted_from": visible["adapted_from"],
        }

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
