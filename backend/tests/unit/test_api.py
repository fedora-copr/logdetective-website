"""
Test the API endpoints.
"""

import json
import os
from base64 import b64encode
from unittest.mock import patch, AsyncMock, MagicMock

import httpx

from src.api import app

FAKE_LOG_CONTENT = "mock build log content"
FAKE_SPEC = {"name": "test.spec", "content": "spec content"}

FAKE_SERVER_RESPONSE = json.dumps(
    {
        "explanation": {"text": "The build failed due to missing dependency."},
        "snippets": [
            {
                "text": "error: package not found",
                "source_file": "build.log",
                "line_number": 42,
            }
        ],
    }
).encode()

RealAsyncClient = httpx.AsyncClient


class TestContributeEndpoints:
    @patch("src.api.CoprProvider")
    async def test_contribute_copr(self, mock_cls, tmp_path):
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

    @patch("src.api.KojiProvider")
    async def test_contribute_koji(self, mock_cls, tmp_path):
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

    @patch("src.api.PackitProvider")
    async def test_contribute_packit(self, mock_cls, tmp_path):
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

    @patch("src.api.URLProvider")
    async def test_contribute_url(self, mock_cls, tmp_path):
        os.environ["FEEDBACK_DIR"] = str(tmp_path / "results")
        url = "https://example.com/build.log"
        b64 = b64encode(url.encode()).decode()
        mock_provider = mock_cls.return_value
        mock_provider.fetch_logs = AsyncMock(
            return_value=[{"name": "Log file", "content": FAKE_LOG_CONTENT}]
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

    @patch("src.api.ContainerProvider")
    async def test_contribute_container(self, mock_cls, tmp_path):
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


class TestExplainEndpoint:
    @patch("src.api._download_log_content", new_callable=AsyncMock)
    @patch("src.api.httpx.AsyncClient")
    async def test_explain_success(self, mock_client_cls, mock_download):
        mock_download.return_value = FAKE_LOG_CONTENT

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = FAKE_SERVER_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_response.request = MagicMock(headers={}, content=b"")

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        transport = httpx.ASGITransport(app=app)
        async with RealAsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/frontend/explain/",
                json={"prompt": "https://example.com/build.log"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "explanation" in data
        assert "extracted_snippets" in data
        assert "log" in data
        assert data["log"]["content"] == FAKE_LOG_CONTENT

    @patch("src.api._download_log_content", new_callable=AsyncMock)
    @patch("src.api.httpx.AsyncClient")
    async def test_explain_server_timeout(self, mock_client_cls, mock_download):
        mock_download.return_value = FAKE_LOG_CONTENT

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ReadTimeout("read timed out"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        transport = httpx.ASGITransport(app=app)
        async with RealAsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/frontend/explain/",
                json={"prompt": "https://example.com/build.log"},
            )

        assert resp.status_code == 408

    @patch("src.api._download_log_content", new_callable=AsyncMock)
    @patch("src.api.httpx.AsyncClient")
    async def test_explain_server_connect_error(self, mock_client_cls, mock_download):
        mock_download.return_value = FAKE_LOG_CONTENT

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.ConnectError("connection refused")
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        transport = httpx.ASGITransport(app=app)
        async with RealAsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/frontend/explain/",
                json={"prompt": "https://example.com/build.log"},
            )

        assert resp.status_code == 408

    @patch("src.api._download_log_content", new_callable=AsyncMock)
    @patch("src.api.httpx.AsyncClient")
    async def test_explain_server_500(self, mock_client_cls, mock_download):
        mock_download.return_value = FAKE_LOG_CONTENT

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.reason_phrase = "Internal Server Error"
        mock_response.url = "http://127.0.0.1:8000/analyze"
        mock_response.request = MagicMock(headers={}, content=b"")
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Server Error",
                request=httpx.Request("POST", "http://127.0.0.1:8000/analyze"),
                response=httpx.Response(500),
            )
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        transport = httpx.ASGITransport(app=app)
        async with RealAsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/frontend/explain/",
                json={"prompt": "https://example.com/build.log"},
            )

        assert resp.status_code == 500


def test_our_server_url(tmp_path):
    from fastapi.testclient import TestClient

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
