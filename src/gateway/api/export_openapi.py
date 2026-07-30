from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings

_CONTRACT = Path(__file__).resolve().parents[3] / "openapi.json"


def _contract_settings(runtime_mode: str) -> Settings:
    values: dict[str, object] = {
        "DIYU_RUNTIME_MODE": runtime_mode,
        "DIYU_APP_DATABASE_URL": "postgresql://diyu_app@localhost/diyu_contract",
        "DIYU_SESSION_SECRET": "openapi-contract-placeholder",
        "DIYU_DEMO_TENANT_ID": "00000000-0000-0000-0000-000000000001",
        "DIYU_DEMO_USER_ID": "00000000-0000-0000-0000-000000000011",
        "DIYU_DEMO_BRAND_ID": "00000000-0000-0000-0000-000000000021",
        "DIYU_DEMO_ACCOUNT_ID": "00000000-0000-0000-0000-000000000031",
        "DIYU_GENERATOR_MODE": "stub",
    }
    if runtime_mode == "production":
        values.update(
            {
                "DIYU_GENERATOR_MODE": "deepseek",
                "DIYU_PUBLIC_URL": "https://diyu.example",
                "DEEPSEEK_API_BASE_URL": "https://example.invalid",
                "DEEPSEEK_API_KEY": "openapi-contract-placeholder",
                "DEEPSEEK_MODEL": "deepseek-v4-flash",
                "DIYU_S3_ENDPOINT_URL": "http://127.0.0.1:9000",
                "DIYU_S3_BUCKET": "diyu-contract",
                "DIYU_S3_ACCESS_KEY_ID": "openapi-contract-placeholder",
                "DIYU_S3_SECRET_ACCESS_KEY": "openapi-contract-placeholder",
                "DIYU_S3_REGION": "us-east-1",
            }
        )
    return Settings.model_validate(values)


def _merge_contract_section(
    contract: dict[str, object],
    production: dict[str, object],
    section: str,
) -> None:
    target = contract.setdefault(section, {})
    source = production.get(section, {})
    if not isinstance(target, dict) or not isinstance(source, dict):
        raise RuntimeError(f"OpenAPI {section} section is invalid")
    target.update(source)


def _stable_contract() -> dict[str, object]:
    contract = create_app(_contract_settings("test")).openapi()
    production = create_app(_contract_settings("production")).openapi()
    _merge_contract_section(contract, production, "paths")
    contract_components = contract.setdefault("components", {})
    production_components = production.get("components", {})
    if not isinstance(contract_components, dict) or not isinstance(production_components, dict):
        raise RuntimeError("OpenAPI components section is invalid")
    for section, values in production_components.items():
        if not isinstance(values, dict):
            raise RuntimeError(f"OpenAPI components.{section} section is invalid")
        target = contract_components.setdefault(section, {})
        if not isinstance(target, dict):
            raise RuntimeError(f"OpenAPI components.{section} target is invalid")
        target.update(values)
    schemas = contract.get("components", {}).get("schemas", {})
    validation_error = schemas.get("ValidationError", {})
    properties = validation_error.get("properties", {})
    if isinstance(properties, dict):
        properties.pop("ctx", None)
        properties.pop("input", None)
    return contract


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(_stable_contract(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not _CONTRACT.exists() or _CONTRACT.read_text(encoding="utf-8") != rendered:
            raise SystemExit("openapi.json is out of date; run make openapi")
        return
    _CONTRACT.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
