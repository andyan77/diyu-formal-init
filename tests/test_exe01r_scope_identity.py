"""EXE-01R R1.4 — the /content bootstrap names the scope with stable ids.

The workspace keys each account's unsent draft on operator + tenant. Those two
used to be a user id and the *brand's display name*, so two brands sharing a
name, or a rename, would have re-homed drafts across accounts. The projection
now carries a trusted tenant id alongside the operator id.

Additive only: every field the shell already published still has to be there
with the same meaning, because other parts of the page read them.
"""

from __future__ import annotations

import json
from typing import cast
from uuid import UUID

from fastapi.testclient import TestClient

from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings
from src.infrastructure.seed_demo import BRAND_ID, TENANT_ID

# Present before this package; none may disappear.
INHERITED_KEYS = frozenset(
    {
        "brand",
        "operator_id",
        "operator",
        "organization",
        "account",
        "platform",
        "content_role",
    }
)


def _bootstrap(response_text: str) -> dict[str, object]:
    marker = "<script>window.__DIYU_BOOTSTRAP__="
    payload = response_text.split(marker, maxsplit=1)[1].split(";</script>", maxsplit=1)[0]
    value = json.loads(payload)
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _identity() -> dict[str, str]:
    with TestClient(create_app(Settings.model_validate({}))) as client:
        client.get("/ui/select/content")
        response = client.get("/content")
        assert response.status_code == 200, response.text
        identity = _bootstrap(response.text).get("identity")
    assert isinstance(identity, dict)
    return {str(key): str(value) for key, value in identity.items()}


def test_content_bootstrap_identity_carries_a_trusted_tenant_id() -> None:
    identity = _identity()

    assert "tenant_id" in identity, "草稿作用域需要稳定租户 id"
    assert "operator_id" in identity, "稳定 operator id 不得回退"
    assert UUID(identity["tenant_id"]) == TENANT_ID
    UUID(identity["operator_id"])


def test_stable_ids_are_never_display_names() -> None:
    identity = _identity()
    display_names = {
        identity["brand"],
        identity["operator"],
        identity["organization"],
        identity["account"],
    }

    for field in ("tenant_id", "operator_id"):
        assert identity[field] not in display_names, f"{field} 退化成了展示名"
        # A display name would not parse; this is the property the draft key
        # actually depends on, so it is asserted rather than inferred.
        UUID(identity[field])

    assert UUID(identity["tenant_id"]) != BRAND_ID, "租户 id 不应等于品牌 id"


def test_the_projection_only_added_fields() -> None:
    identity = _identity()
    missing = INHERITED_KEYS - set(identity)
    assert not missing, f"bootstrap 身份丢失既有字段：{sorted(missing)}"
    assert identity["brand"] and not identity["brand"].strip().startswith("00000000")
