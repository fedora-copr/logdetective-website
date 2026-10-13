"""
Test the API /contribute endpoints.
"""

import os
from base64 import b64encode
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api import app

FAKE_LOG_CONTENT = "mock build log content"
FAKE_SPEC = {"name": "test.spec", "content": "spec content"}


@pytest.fixture(autouse=True)
def _provide_app_http_client():
    """Ensure app.state.http_client exists for tests that bypass lifespan."""
    app.state.http_client = MagicMock()


class TestContributeEndpoints:
    """Tests for contribution build-log endpoints."""

    @patch("src.api_contribute.CoprProvider")
    async def test_contribute_copr(self, mock_cls, tmp_path):
        """Return Copr build logs and spec data."""
        os.environ["FEEDBACK_DIR"] = str(tmp_path / "results")
        mock_provider = mock_cls.return_value
        mock_provider.fetch_logs = AsyncMock(
            return_value=[{"name": "build.log", "content": FAKE_LOG_CONTENT}]
        )
        mock_provider.fetch_spec_file = AsyncMock(return_value=FAKE_SPEC)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/frontend/contribute/copr/123/fedora-39-x86_64")

        assert resp.status_code == 200
        data = resp.json()
        assert data["build_id"] == 123
        assert data["build_id_title"] == "Copr build"
        assert "copr.fedorainfracloud.org" in data["build_url"]
        assert len(data["logs"]) == 1
        assert data["spec_file"]["name"] == "test.spec"

    @patch("src.api_contribute.KojiProvider")
    async def test_contribute_koji(self, mock_cls, tmp_path):
        """Return Koji build logs and spec data."""
        os.environ["FEEDBACK_DIR"] = str(tmp_path / "results")
        mock_provider = mock_cls.return_value
        mock_provider.fetch_logs = AsyncMock(
            return_value=[{"name": "build.log", "content": FAKE_LOG_CONTENT}]
        )
        mock_provider.fetch_spec_file = AsyncMock(return_value=None)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/frontend/contribute/koji/456/x86_64")

        assert resp.status_code == 200
        data = resp.json()
        assert data["build_id"] == 456
        assert data["build_id_title"] == "Koji build"
        assert "koji.fedoraproject.org" in data["build_url"]

    @patch("src.api_contribute.PackitProvider")
    async def test_contribute_packit(self, mock_cls, tmp_path):
        """Return Packit build logs and source URL."""
        os.environ["FEEDBACK_DIR"] = str(tmp_path / "results")
        mock_provider = mock_cls.return_value
        mock_provider.fetch_logs = AsyncMock(
            return_value=[{"name": "build.log", "content": FAKE_LOG_CONTENT}]
        )
        mock_provider.fetch_spec_file = AsyncMock(return_value=None)
        mock_provider.get_url = AsyncMock(
            return_value="https://dashboard.packit.dev/results/copr-builds/789"
        )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/frontend/contribute/packit/789")

        assert resp.status_code == 200
        data = resp.json()
        assert data["build_id"] == 789
        assert data["build_id_title"] == "Packit build"
        assert "packit.dev" in data["build_url"]

    @patch("src.api_contribute.URLProvider")
    async def test_contribute_url(self, mock_cls, tmp_path):
        """Return logs fetched from the supplied URL."""
        os.environ["FEEDBACK_DIR"] = str(tmp_path / "results")
        url = "https://example.com/build.log"
        b64 = b64encode(url.encode()).decode()
        mock_provider = mock_cls.return_value
        mock_provider.fetch_logs = AsyncMock(
            return_value=[{"name": "build.log", "content": FAKE_LOG_CONTENT}]
        )
        mock_provider.fetch_spec_file = AsyncMock(return_value=None)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get(f"/frontend/contribute/url/{b64}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["build_url"] == url
        assert data["build_id_title"] == "URL"

    @patch("src.api_contribute.ContainerProvider")
    async def test_contribute_container(self, mock_cls, tmp_path):
        """Return logs fetched from the supplied container URL."""
        os.environ["FEEDBACK_DIR"] = str(tmp_path / "results")
        url = "https://example.com/container.log"
        b64 = b64encode(url.encode()).decode()
        mock_provider = mock_cls.return_value
        mock_provider.fetch_logs = AsyncMock(
            return_value=[{"name": "Container log", "content": FAKE_LOG_CONTENT}]
        )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get(f"/frontend/contribute/container/{b64}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["build_url"] == url
        assert data["build_id_title"] == "Container log"
        assert len(data["logs"]) == 1

    @patch("src.api_contribute.OBSProvider")
    async def test_contribute_obs(self, mock_cls, tmp_path):
        """POST /frontend/contribute/obs feedback and returns OK."""
        os.environ["FEEDBACK_DIR"] = str(tmp_path / "results")
        mock_provider = mock_cls.return_value
        mock_provider.fetch_logs = AsyncMock(
            return_value=[{"name": "build.log", "content": FAKE_LOG_CONTENT}]
        )
        mock_provider.fetch_spec_file = AsyncMock(return_value=None)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get(
                "/frontend/contribute/obs/openSUSE:Factory/standard/x86_64/ed"
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["build_id"] is None
        assert data["build_id_title"] == "OBS build"
        assert data["build_url"] == (
            "https://build.opensuse.org/package/show/openSUSE:Factory/ed"
        )
        assert len(data["logs"]) == 1
        assert data["spec_file"] is None
        mock_cls.assert_called_once_with(
            "openSUSE:Factory",
            "standard",
            "x86_64",
            "ed",
            http_client=app.state.http_client,
        )


def test_our_server_url(tmp_path):
    """Test that the /frontend/contribute/copr endpoint returns URLs with the correct base URL."""

    client = TestClient(app)
    os.environ["FEEDBACK_DIR"] = str(tmp_path / "results")
    data = {
        "username": "FAS:me",
        "fail_reason": "Failed because...",
        "how_to_fix": "Like this...",
        "spec_file": {
            "name": "llvm.spec",
            "content": "Yes, the actual content of the spec file",
        },
        "logs": [
            {
                "name": "build.log",
                "content": "content of the build log",
                "snippets": [
                    {
                        "start_index": 1,
                        "end_index": 2,
                        "user_comment": "this snippet is relevant because...",
                        "text": "content of the snippet",
                    }
                ],
            }
        ],
    }
    response = client.post("/frontend/contribute/copr/1/x86_64", json=data)
    assert response.status_code == 200
    response_json = response.json()
    assert response_json["review_url_json"].startswith(
        f"{client.base_url}/frontend/review/"
    )
    assert response_json["review_url_website"].startswith(f"{client.base_url}/review/")
