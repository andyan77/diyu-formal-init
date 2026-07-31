from __future__ import annotations

from src.brain.content_control_service import ContentControlService
from src.brain.content_service import ContentService
from src.brain.display_service import DisplayService
from src.brain.dm01_display_compiler import DM01DisplayCompiler
from src.brain.workbench_service import WorkbenchService
from src.gateway.api.settings import Settings
from src.infrastructure.content_control_repository import PostgresContentControlRepository
from src.infrastructure.display_repository import PostgresDisplayRepository
from src.infrastructure.local_object_store import LocalObjectStore
from src.infrastructure.postgres_repository import PostgresContentRepository
from src.infrastructure.s3_object_store import S3ObjectStore
from src.infrastructure.workbench_repository import PostgresWorkbenchRepository
from src.ports.content_generator import ContentGenerator
from src.ports.material_object_store import MaterialObjectStore
from src.shared.service_status import ProviderStatusTracker
from src.tool.llm_gateway.deepseek import DeepSeekGenerator
from src.tool.llm_gateway.stub import DeterministicP1Generator


def _object_store(settings: Settings) -> MaterialObjectStore:
    """Media bytes always stay behind the object-store port, never in relational metadata."""
    if not settings.is_production:
        return LocalObjectStore(settings.material_storage_root)
    endpoint_url = settings.s3_endpoint_url
    bucket = settings.s3_bucket
    access_key_id = settings.s3_access_key_id
    secret_access_key = settings.s3_secret_access_key
    region = settings.s3_region
    if endpoint_url is None or bucket is None or access_key_id is None or secret_access_key is None or region is None:
        raise RuntimeError("production 对象存储配置不完整")
    return S3ObjectStore(
        endpoint_url,
        bucket,
        access_key_id.get_secret_value(),
        secret_access_key.get_secret_value(),
        region,
    )


def build_content_control_service(settings: Settings) -> ContentControlService:
    """One versioned catalog, one account profile surface and one private preference surface."""
    return ContentControlService(
        PostgresContentControlRepository(settings.app_database_url),
        _object_store(settings),
    )


def build_content_service(settings: Settings) -> ContentService:
    status_tracker = ProviderStatusTracker()
    generator: ContentGenerator
    if settings.generator_mode == "stub":
        generator = DeterministicP1Generator()
    else:
        if (
            settings.deepseek_api_base_url is None
            or settings.deepseek_api_key is None
            or settings.deepseek_model is None
        ):
            raise RuntimeError("DeepSeek Writer 配置不完整")
        generator = DeepSeekGenerator(
            api_base_url=settings.deepseek_api_base_url,
            api_key=settings.deepseek_api_key.get_secret_value(),
            model=settings.deepseek_model,
            timeout_seconds=settings.model_timeout_seconds,
            max_retries=settings.model_max_retries,
            status_tracker=status_tracker,
        )
    return ContentService(
        PostgresContentRepository(
            settings.app_database_url,
            None if settings.is_production else settings.demo_store_content_account_id,
            settings.store_active_product_refs,
        ),
        generator,
        build_content_control_service(settings),
        status_tracker,
    )


def build_display_service(settings: Settings) -> DisplayService:
    """DM01 is always compiled from trusted display facts, never from an LLM."""
    return DisplayService(PostgresDisplayRepository(settings.app_database_url), DM01DisplayCompiler())


def build_workbench_service(settings: Settings) -> WorkbenchService:
    """One minimal workbench metadata service; media bytes stay behind an object-store port."""
    return WorkbenchService(
        PostgresWorkbenchRepository(settings.app_database_url),
        _object_store(settings),
    )
