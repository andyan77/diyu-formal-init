from __future__ import annotations

from uuid import UUID

from src.brain.natural_entry import (
    is_natural_chat,
    natural_reply,
    requests_continuation,
    sanitize_seed,
)
from src.brain.p1_contract import assert_content_complete
from src.ports.content_generator import ContentGenerator
from src.ports.content_repository import ContentRepository
from src.shared.errors import GenerationFailed
from src.shared.types import (
    ActiveAsset,
    BrandContext,
    ContentProduct,
    GenerationInput,
    ProductFact,
    RoutingInput,
    TrustedScope,
)


class ContentService:
    def __init__(self, repository: ContentRepository, generator: ContentGenerator) -> None:
        self._repository = repository
        self._generator = generator

    def create_from_weak_seed(
        self, scope: TrustedScope, weak_seed: str, reuse_version_id: UUID | None = None
    ) -> dict[str, object]:
        if reuse_version_id is None and is_natural_chat(weak_seed):
            return {"kind": "greeting", "message": natural_reply()}
        if reuse_version_id is None and requests_continuation(weak_seed):
            reuse_version_id = self._repository.latest_visible_version(scope)
            if reuse_version_id is None:
                return {"kind": "greeting", "message": "还没有当前账号可继续的上一条内容。"}
        sanitized_seed = sanitize_seed(weak_seed)
        context = self._repository.load_brand_context(scope)
        products = self._repository.load_product_facts(scope, sanitized_seed)
        prior_for_route = (
            self._repository.fetch_version_body(scope, reuse_version_id) if reuse_version_id is not None else None
        )
        primary_product = self._generator.route(
            RoutingInput(sanitized_seed, context, products, prior_for_route)
        )
        if primary_product is None:
            return {"kind": "greeting", "message": natural_reply()}
        if primary_product == "visual_styling_story" and not products:
            return {"kind": "question", "message": "这条视觉内容要以哪件当前品牌商品为锚？"}
        assets = self._repository.load_active_assets(scope, primary_product, sanitized_seed, products)
        task_id, run_id, prior_body = self._repository.create_task_and_running_run(
            scope,
            sanitized_seed,
            primary_product,
            reuse_version_id,
            self._generator.model_name,
            assets,
            context,
            products,
        )
        return self._generate_and_persist(
            scope, task_id, run_id, sanitized_seed, primary_product, None, prior_body, context, assets, products
        )

    def revise(self, scope: TrustedScope, task_id: UUID, instruction: str) -> dict[str, object]:
        context = self._repository.load_brand_context(scope)
        weak_seed, primary_product = self._repository.task_details(scope, task_id)
        products = self._repository.load_task_product_facts(scope, task_id)
        assets = self._repository.load_active_assets(scope, primary_product, weak_seed, products)
        run_id, parent_version_id, weak_seed, primary_product = self._repository.revise_task(
            scope, task_id, instruction, self._generator.model_name, assets, context, products
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
        )

    def fetch_version(self, scope: TrustedScope, task_id: UUID, version: int) -> dict[str, object]:
        return self._repository.fetch_version(scope, task_id, version)

    def save_version(self, scope: TrustedScope, version_id: UUID) -> dict[str, object]:
        return self._repository.save_version(scope, version_id)

    def identity_summary(self, scope: TrustedScope) -> dict[str, str]:
        context = self._repository.load_brand_context(scope)
        return {
            "brand": context.brand_name,
            "operator": context.operator_name,
            "organization": context.organization_name,
            "account": context.account_name,
            "content_role": context.content_role_name,
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
                    active_domain_assets=assets,
                    products=products,
                    prior_saved_body=prior_saved_body,
                )
            )
            assert_content_complete(artifact)
        except GenerationFailed as exc:
            self._repository.fail_run(scope, task_id, run_id, str(exc))
            raise
        except Exception as exc:  # Provider implementation details never reach the user.
            self._repository.fail_run(scope, task_id, run_id, "模型调用失败，请稍后重试")
            raise GenerationFailed("模型调用失败，请稍后重试") from exc
        return self._repository.complete_run_with_version(
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
        ) | {"kind": "content"}
