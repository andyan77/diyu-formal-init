from __future__ import annotations

from fastapi.testclient import TestClient

from src.gateway.api.app import create_app
from src.gateway.api.settings import Settings

_TASK = "11111111-1111-4111-8111-111111111111"


def _client() -> TestClient:
    return TestClient(create_app(Settings.model_validate({})), follow_redirects=False)


def test_old_materials_address_moves_without_losing_its_query(
    app_database_url: str,
) -> None:
    """`/organization-materials` was renamed to `/materials` (EXE-01 SEAM-06)."""
    with _client() as client:
        moved = client.get("/organization-materials")
        assert moved.status_code == 303
        assert moved.headers["location"] == "/materials"

        with_query = client.get("/organization-materials?publishing_identity_id=x")
        assert with_query.status_code == 303
        assert with_query.headers["location"] == "/materials?publishing_identity_id=x"


def test_task_query_form_canonicalises_to_the_task_route(
    app_database_url: str,
) -> None:
    """`workbench_location` still emits `/content?task=…`; it must land on the task."""
    with _client() as client:
        response = client.get(
            f"/content?task={_TASK}&version=2&notice=saved&target=douyin_video"
        )
        assert response.status_code == 303
        location = response.headers["location"]
        assert location.startswith(f"/content/tasks/{_TASK}?")
        assert "version=2" in location
        assert "target=douyin_video" in location
        assert "notice=saved" in location


def test_task_route_is_registered_and_guarded(app_database_url: str) -> None:
    """The new route reuses content_workbench, so it refuses anonymous callers."""
    with _client() as client:
        assert client.get(f"/content/tasks/{_TASK}?version=2").status_code == 401


def test_task_route_does_not_redirect_to_itself(app_database_url: str) -> None:
    """The canonicalisation is guarded by path, or the two routes would loop."""
    with _client() as client:
        response = client.get(f"/content/tasks/{_TASK}")
        assert response.status_code != 303


def test_unknown_paths_do_not_fall_back_to_the_public_home(
    app_database_url: str,
) -> None:
    """A mistyped or not-yet-built path must say so, not serve the marketing page."""
    with _client() as client:
        for path in ("/no-such-page", "/content/projects", "/user/nope"):
            response = client.get(path)
            assert response.status_code == 404, path
            assert '"application": "public"' not in response.text, path
