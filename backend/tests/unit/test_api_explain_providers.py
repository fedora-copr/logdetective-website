"""
Test the API /explain endpoints.
"""

# Endpoint cases keep their setup local for readability.
# pylint: disable=duplicate-code

from base64 import b64encode
from unittest.mock import AsyncMock, patch

import httpx

from src.api import app

FAKE_LOG_CONTENT = "mock build log content"
FAKE_SPEC = {"name": "test.spec", "content": "spec content"}


def _server_response(status_code, *, url, headers=None, json_data=None):
    request = httpx.Request("GET" if status_code == 200 else "POST", url)
    return httpx.Response(
        status_code,
        headers=headers,
        json=json_data,
        request=request,
    )


RealAsyncClient = httpx.AsyncClient


class TestExplainProviderEndpoints:
    """Tests for provider-specific explain endpoints."""

    @patch("src.api_explain._call_analyze_api", new_callable=AsyncMock)
    @patch("src.api_explain.CoprProvider")
    async def test_explain_copr(self, mock_cls, mock_analyze):
        """Analyze logs from a Copr build."""
        mock_provider = mock_cls.return_value
        mock_provider.fetch_log_urls = AsyncMock(
            return_value=[
                {"name": "build.log", "url": "https://copr.example.com/build.log"}
            ]
        )
        mock_provider.fetch_logs = AsyncMock(
            return_value=[{"name": "build.log", "content": FAKE_LOG_CONTENT}]
        )
        mock_provider.fetch_spec_file = AsyncMock(return_value=FAKE_SPEC)
        mock_analyze.return_value = {
            "explanation": "The build failed due to missing dependency.",
            "extracted_snippets": [
                {
                    "snippet": "error: package not found",
                    "source_file": "build.log",
                    "line_number": 42,
                }
            ],
        }

        transport = httpx.ASGITransport(app=app)
        async with RealAsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post("/frontend/explain/copr/123/fedora-39-x86_64")

        assert resp.status_code == 200
        data = resp.json()
        assert "explanation" in data
        assert "extracted_snippets" in data
        assert "logs" in data
        assert len(data["logs"]) == 1
        assert data["logs"][0]["content"] == FAKE_LOG_CONTENT

    @patch("src.api_explain._call_analyze_api", new_callable=AsyncMock)
    @patch("src.api_explain.KojiProvider")
    async def test_explain_koji(self, mock_cls, mock_analyze):
        """Analyze logs from a Koji build."""
        mock_provider = mock_cls.return_value
        mock_provider.fetch_log_urls = AsyncMock(
            return_value=[
                {"name": "build.log", "url": "https://kojipkgs.example.com/build.log"}
            ]
        )
        mock_provider.fetch_logs = AsyncMock(
            return_value=[{"name": "build.log", "content": FAKE_LOG_CONTENT}]
        )
        mock_provider.fetch_spec_file = AsyncMock(return_value=None)
        mock_analyze.return_value = {
            "explanation": "Build failed.",
            "extracted_snippets": [],
        }

        transport = httpx.ASGITransport(app=app)
        async with RealAsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post("/frontend/explain/koji/456/x86_64")

        assert resp.status_code == 200
        data = resp.json()
        assert "explanation" in data
        assert "logs" in data

    @patch("src.api_explain._call_analyze_api", new_callable=AsyncMock)
    @patch("src.api_explain.PackitProvider")
    async def test_explain_packit(self, mock_cls, mock_analyze):
        """Analyze logs from a Packit build."""
        mock_provider = mock_cls.return_value
        mock_provider.fetch_log_urls = AsyncMock(
            return_value=[{"name": "build.log", "url": "https://example.com/build.log"}]
        )
        mock_provider.fetch_logs = AsyncMock(
            return_value=[{"name": "build.log", "content": FAKE_LOG_CONTENT}]
        )
        mock_provider.fetch_spec_file = AsyncMock(return_value=None)
        mock_analyze.return_value = {
            "explanation": "Build failed.",
            "extracted_snippets": [],
        }

        transport = httpx.ASGITransport(app=app)
        async with RealAsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post("/frontend/explain/packit/789")

        assert resp.status_code == 200
        data = resp.json()
        assert "explanation" in data
        assert "logs" in data

    @patch("src.api_explain._call_analyze_api", new_callable=AsyncMock)
    @patch("src.api_explain.URLProvider")
    async def test_explain_url(self, mock_cls, mock_analyze):
        """Analyze logs from the supplied URL."""
        url = "https://example.com/build.log"
        b64 = b64encode(url.encode()).decode()
        mock_provider = mock_cls.return_value
        mock_provider.fetch_log_urls = AsyncMock(
            return_value=[{"name": "build.log", "url": url}]
        )
        mock_provider.fetch_logs = AsyncMock(
            return_value=[{"name": "build.log", "content": FAKE_LOG_CONTENT}]
        )
        mock_analyze.return_value = {
            "explanation": "Build failed.",
            "extracted_snippets": [],
        }

        transport = httpx.ASGITransport(app=app)
        async with RealAsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(f"/frontend/explain/url/{b64}")

        assert resp.status_code == 200
        data = resp.json()
        assert "explanation" in data
        assert "logs" in data

    @patch("src.api_explain._call_analyze_api", new_callable=AsyncMock)
    @patch("src.api_explain.ContainerProvider")
    async def test_explain_container(self, mock_cls, mock_analyze):
        """Analyze logs from the supplied container URL."""
        url = "https://example.com/container.log"
        b64 = b64encode(url.encode()).decode()
        mock_provider = mock_cls.return_value
        mock_provider.fetch_log_urls = AsyncMock(
            return_value=[{"name": "Container log", "url": url}]
        )
        mock_provider.fetch_logs = AsyncMock(
            return_value=[{"name": "Container log", "content": FAKE_LOG_CONTENT}]
        )
        mock_analyze.return_value = {
            "explanation": "Build failed.",
            "extracted_snippets": [],
        }

        transport = httpx.ASGITransport(app=app)
        async with RealAsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(f"/frontend/explain/container/{b64}")

        assert resp.status_code == 200
        data = resp.json()
        assert "explanation" in data
        assert "logs" in data

    @patch("src.api_explain._call_analyze_api", new_callable=AsyncMock)
    @patch("src.api_explain.OBSProvider")
    async def test_explain_obs(self, mock_cls, mock_analyze):
        """POST /frontend/explain/obs forwards an OBS log to the logdetective server."""
        log_url = (
            "https://build.opensuse.org/public/build/"
            "openSUSE:Factory/standard/x86_64/ed/_log"
        )
        mock_provider = mock_cls.return_value
        mock_provider.fetch_log_urls = AsyncMock(
            return_value=[{"name": "build.log", "url": log_url}]
        )
        mock_provider.fetch_logs = AsyncMock(
            return_value=[{"name": "build.log", "content": FAKE_LOG_CONTENT}]
        )
        mock_provider.fetch_spec_file = AsyncMock(return_value=None)
        mock_analyze.return_value = {
            "explanation": "Build failed.",
            "extracted_snippets": [],
        }

        transport = httpx.ASGITransport(app=app)
        async with RealAsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/frontend/explain/obs/openSUSE:Factory/standard/x86_64/ed"
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "explanation" in data
        assert "logs" in data
        mock_cls.assert_called_once_with(
            "openSUSE:Factory",
            "standard",
            "x86_64",
            "ed",
            http_client=app.state.http_client,
        )

    @patch("src.analysis._check_log_urls", new_callable=AsyncMock)
    @patch("src.api_explain.CoprProvider")
    async def test_explain_provider_timeout(self, mock_cls, _mock_check):
        """Return a gateway timeout when provider analysis times out."""
        mock_provider = mock_cls.return_value
        mock_provider.fetch_log_urls = AsyncMock(
            return_value=[{"name": "build.log", "url": "https://example.com/build.log"}]
        )
        mock_provider.fetch_logs = AsyncMock(
            return_value=[{"name": "build.log", "content": FAKE_LOG_CONTENT}]
        )
        mock_provider.fetch_spec_file = AsyncMock(return_value=None)

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ReadTimeout("read timed out"))
        app.state.http_client = mock_client

        transport = httpx.ASGITransport(app=app)
        async with RealAsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post("/frontend/explain/copr/123/fedora-39-x86_64")

        assert resp.status_code == 504

    @patch("src.analysis._check_log_urls", new_callable=AsyncMock)
    @patch("src.api_explain.CoprProvider")
    async def test_explain_provider_server_error(self, mock_cls, _mock_check):
        """Return an error when the analysis service fails."""
        mock_provider = mock_cls.return_value
        mock_provider.fetch_log_urls = AsyncMock(
            return_value=[{"name": "build.log", "url": "https://example.com/build.log"}]
        )
        mock_provider.fetch_logs = AsyncMock(
            return_value=[{"name": "build.log", "content": FAKE_LOG_CONTENT}]
        )
        mock_provider.fetch_spec_file = AsyncMock(return_value=None)

        mock_response = _server_response(
            500,
            url="http://127.0.0.1:8000/analyze",
            json_data={"detail": "Server Error"},
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        app.state.http_client = mock_client

        transport = httpx.ASGITransport(app=app)
        async with RealAsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post("/frontend/explain/copr/123/fedora-39-x86_64")

        assert resp.status_code == 500
