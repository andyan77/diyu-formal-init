from __future__ import annotations

from src.brain.content_service import ContentService
from src.brain.display_service import DisplayService
from src.brain.dm01_display_compiler import DM01DisplayCompiler
from src.brain.workbench_service import WorkbenchService
from src.gateway.api.settings import Settings
from src.infrastructure.display_repository import PostgresDisplayRepository
from src.infrastructure.local_object_store import LocalObjectStore
from src.infrastructure.postgres_repository import PostgresContentRepository
from src.infrastructure.workbench_repository import PostgresWorkbenchRepository
from src.ports.content_generator import ContentGenerator
from src.tool.llm_gateway.deepseek import DeepSeekGenerator
from src.tool.llm_gateway.stub import DeterministicP1Generator


def build_content_service(settings: Settings) -> ContentService:
    generator: ContentGenerator
    if settings.generator_mode == "stub":
        generator = DeterministicP1Generator()
    else:
        if (
            settings.deepseek_api_base_url is None
            or settings.deepseek_api_key is None
            or settings.deepseek_model is None
        ):
            raise RuntimeError("DeepSeek 配置不完整")
        generator = DeepSeekGenerator(
            api_base_url=settings.deepseek_api_base_url,
            api_key=settings.deepseek_api_key.get_secret_value(),
            model=settings.deepseek_model,
            timeout_seconds=settings.model_timeout_seconds,
            max_retries=settings.model_max_retries,
        )
    return ContentService(
        PostgresContentRepository(
            settings.app_database_url,
            settings.demo_store_content_account_id,
            settings.store_active_product_refs,
        ),
        generator,
    )


def build_display_service(settings: Settings) -> DisplayService:
    """DM01 is always compiled from trusted display facts, never from an LLM."""
    return DisplayService(
        PostgresDisplayRepository(settings.app_database_url), DM01DisplayCompiler()
    )


def build_workbench_service(settings: Settings) -> WorkbenchService:
    """One minimal workbench metadata service; media bytes stay behind an object-store port."""
    return WorkbenchService(
        PostgresWorkbenchRepository(settings.app_database_url),
        LocalObjectStore(settings.material_storage_root),
    )
