"""
Test the API endpoints.
"""

import os
import tarfile
from base64 import b64encode
from datetime import date
from unittest.mock import call, patch, AsyncMock, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException

from src.api import app
from src.constants import LOGDETECTIVE_READ_TIMEOUT


@pytest.fixture(autouse=True)
def _provide_app_http_client():
    """Ensure app.state.http_client exists for tests that bypass lifespan."""
    app.state.http_client = MagicMock()
    with patch("src.api.sleep", new_callable=AsyncMock):
        yield


FAKE_LOG_CONTENT = "mock build log content"
FAKE_SPEC = {"name": "test.spec", "content": "spec content"}

FAKE_SERVER_RESPONSE = {
    "explanation": "The build failed due to missing dependency.",
    "snippets": [
        {
            "text": "error: package not found",
            "source_file": "build.log",
            "line_number": 42,
        }
    ],
}

FAKE_PROCESSED_RESPONSE = {
    "explanation": "The build failed due to missing dependency.",
    "extracted_snippets": [
        {
            "snippet": "error: package not found",
            "source_file": "build.log",
            "line_number": 42,
        }
    ],
}


def _server_response(status_code, *, url, headers=None, json_data=None):
    request = httpx.Request("GET" if status_code == 200 else "POST", url)
    return httpx.Response(
        status_code,
        headers=headers,
        json=json_data,
        request=request,
    )


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

    @patch("src.api.OBSProvider")
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


class TestExplainEndpoint:
    @patch("src.api._poll_for_analysis_task", new_callable=AsyncMock)
    @patch("src.api._check_log_urls", new_callable=AsyncMock)
    @patch("src.api._download_log_content", new_callable=AsyncMock)
    async def test_explain_success(self, mock_download, _mock_check, mock_poll):
        mock_download.return_value = FAKE_LOG_CONTENT
        mock_poll.return_value = FAKE_PROCESSED_RESPONSE

        submit_response = _server_response(
            202,
            url="http://127.0.0.1:8000/analyze",
            headers={
                "Location": "http://127.0.0.1:8000/tasks/task-id",
                "Retry-After": "0",
            },
        )
        task_response = _server_response(
            200,
            url="http://127.0.0.1:8000/tasks/task-id",
            json_data={"status": "done", "result": FAKE_SERVER_RESPONSE},
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=submit_response)
        mock_client.get = AsyncMock(return_value=task_response)
        app.state.http_client = mock_client

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
        assert "logs" in data
        assert len(data["logs"]) == 1
        assert data["logs"][0]["content"] == FAKE_LOG_CONTENT

    @patch("src.api._check_log_urls", new_callable=AsyncMock)
    @patch("src.api._download_log_content", new_callable=AsyncMock)
    @patch("src.api.sleep", new_callable=AsyncMock)
    async def test_explain_polls_until_task_is_done(
        self, mock_sleep, mock_download, _mock_check
    ):
        mock_download.return_value = FAKE_LOG_CONTENT
        submit_response = _server_response(
            202,
            url="http://127.0.0.1:8000/analyze",
            headers={
                "Location": "http://127.0.0.1:8000/tasks/task-id",
                "Retry-After": "2",
            },
        )
        active_response = _server_response(
            200,
            url="http://127.0.0.1:8000/tasks/task-id",
            json_data={"status": "in_progress"},
        )
        done_response = _server_response(
            200,
            url="http://127.0.0.1:8000/tasks/task-id",
            json_data={"status": "done", "result": FAKE_SERVER_RESPONSE},
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=submit_response)
        mock_client.get = AsyncMock(side_effect=[active_response, done_response])
        app.state.http_client = mock_client

        transport = httpx.ASGITransport(app=app)
        async with RealAsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/frontend/explain/",
                json={"prompt": "https://example.com/build.log"},
            )

        assert resp.status_code == 200
        assert resp.json()["explanation"] == FAKE_SERVER_RESPONSE["explanation"]
        polled_urls = [request.args[0] for request in mock_client.get.await_args_list]
        assert polled_urls == [
            "http://127.0.0.1:8000/tasks/task-id",
            "http://127.0.0.1:8000/tasks/task-id",
        ]
        mock_sleep.assert_has_awaits([call(2.0), call(2.0)])

    @patch("src.api._check_log_urls", new_callable=AsyncMock)
    @patch("src.api._download_log_content", new_callable=AsyncMock)
    async def test_explain_submission_missing_location(
        self, mock_download, _mock_check
    ):
        mock_download.return_value = FAKE_LOG_CONTENT
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            return_value=_server_response(
                202, url="http://127.0.0.1:8000/analyze", headers={}
            )
        )
        app.state.http_client = mock_client

        transport = httpx.ASGITransport(app=app)
        async with RealAsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/frontend/explain/",
                json={"prompt": "https://example.com/build.log"},
            )

        assert resp.status_code == 502
        assert "invalid task headers" in resp.json()["description"]

    @pytest.mark.parametrize(
        ("result", "expected_status"),
        [
            (None, 502),
            ({}, 502),
            ({"snippets": []}, 502),
            ({"snippets": None}, 502),
            ({"explanation": "text", "snippets": "invalid"}, 502),
            ({"explanation": "text", "snippets": [{"invalid_key": "text"}]}, 502),
            ({"explanation": "text"}, 200),
            ({"explanation": "text", "snippets": None}, 200),
        ],
    )
    @patch("src.api._check_log_urls", new_callable=AsyncMock)
    @patch("src.api._download_log_content", new_callable=AsyncMock)
    async def test_explain_result_validation(
        self, mock_download, _mock_check, result, expected_status
    ):
        mock_download.return_value = FAKE_LOG_CONTENT
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            return_value=_server_response(
                202,
                url="http://127.0.0.1:8000/analyze",
                headers={"Location": "http://127.0.0.1:8000/tasks/task-id"},
            )
        )
        mock_client.get = AsyncMock(
            return_value=_server_response(
                200,
                url="http://127.0.0.1:8000/tasks/task-id",
                json_data={"status": "done", "result": result},
            )
        )
        app.state.http_client = mock_client

        transport = httpx.ASGITransport(app=app)
        async with RealAsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/frontend/explain/",
                json={"prompt": "https://example.com/build.log"},
            )

        assert resp.status_code == expected_status
        if expected_status == 200:
            assert resp.json()["extracted_snippets"] == []
        else:
            assert "Could not obtain" in resp.json()["description"]

    @pytest.mark.parametrize(
        ("failure", "expected_status"),
        [
            (httpx.ReadTimeout("read timed out"), 504),
            (httpx.ConnectError("connection refused"), 502),
            (
                _server_response(
                    500,
                    url="http://127.0.0.1:8000/tasks/task-id",
                    json_data={"detail": "poll failed"},
                ),
                500,
            ),
        ],
    )
    @patch("src.api._check_log_urls", new_callable=AsyncMock)
    @patch("src.api._download_log_content", new_callable=AsyncMock)
    async def test_explain_polling_get_failure(
        self, mock_download, _mock_check, failure, expected_status
    ):
        mock_download.return_value = FAKE_LOG_CONTENT
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            return_value=_server_response(
                202,
                url="http://127.0.0.1:8000/analyze",
                headers={"Location": "http://127.0.0.1:8000/tasks/task-id"},
            )
        )
        if isinstance(failure, Exception):
            mock_client.get = AsyncMock(side_effect=failure)
        else:
            mock_client.get = AsyncMock(return_value=failure)
        app.state.http_client = mock_client

        transport = httpx.ASGITransport(app=app)
        async with RealAsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/frontend/explain/",
                json={"prompt": "https://example.com/build.log"},
            )

        assert resp.status_code == expected_status

    @patch("src.api._poll_for_analysis_task", new_callable=AsyncMock)
    @patch("src.api._check_log_urls", new_callable=AsyncMock)
    @patch("src.api._download_log_content", new_callable=AsyncMock)
    async def test_explain_polling_timeout(self, mock_download, _mock_check, mock_poll):
        mock_download.return_value = FAKE_LOG_CONTENT
        mock_poll.side_effect = TimeoutError
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            return_value=_server_response(
                202,
                url="http://127.0.0.1:8000/analyze",
                headers={"Location": "http://127.0.0.1:8000/tasks/task-id"},
            )
        )
        app.state.http_client = mock_client

        transport = httpx.ASGITransport(app=app)
        async with RealAsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/frontend/explain/",
                json={"prompt": "https://example.com/build.log"},
            )

        assert resp.status_code == 504
        detail = resp.json()["description"]
        assert "task-id" in detail
        assert f"{LOGDETECTIVE_READ_TIMEOUT} seconds" in detail

    @patch("src.api.LOG_DETECTIVE_TOKEN", "test-token")
    @patch("src.api._poll_for_analysis_task", new_callable=AsyncMock)
    @patch("src.api._check_log_urls", new_callable=AsyncMock)
    @patch("src.api._download_log_content", new_callable=AsyncMock)
    async def test_explain_forwards_authorization_on_submission_and_poll(
        self, mock_download, _mock_check, mock_poll
    ):
        mock_download.return_value = FAKE_LOG_CONTENT
        mock_poll.return_value = FAKE_PROCESSED_RESPONSE
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            return_value=_server_response(
                202,
                url="http://127.0.0.1:8000/analyze",
                headers={"Location": "http://127.0.0.1:8000/tasks/task-id"},
            )
        )
        mock_client.get = AsyncMock(
            return_value=_server_response(
                200,
                url="http://127.0.0.1:8000/tasks/task-id",
                json_data={"status": "done", "result": FAKE_SERVER_RESPONSE},
            )
        )
        app.state.http_client = mock_client

        transport = httpx.ASGITransport(app=app)
        async with RealAsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/frontend/explain/",
                json={"prompt": "https://example.com/build.log"},
            )

        assert resp.status_code == 200
        expected_headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer test-token",
        }
        assert mock_client.post.await_args.kwargs["headers"] == expected_headers
        assert mock_poll.await_args.args[3] == expected_headers

    @pytest.mark.parametrize(
        ("status", "task", "expected_detail"),
        [
            (
                "error",
                {"status": "error", "error": {"message": "Inference failed"}},
                "Inference failed",
            ),
            (
                "cancelled",
                {"status": "cancelled"},
                "Analysis task was cancelled",
            ),
        ],
    )
    @patch("src.api._check_log_urls", new_callable=AsyncMock)
    @patch("src.api._download_log_content", new_callable=AsyncMock)
    async def test_explain_terminal_task_failure(
        self,
        mock_download,
        _mock_check,
        status,
        task,
        expected_detail,
    ):
        mock_download.return_value = FAKE_LOG_CONTENT
        submit_response = _server_response(
            202,
            url="http://127.0.0.1:8000/analyze",
            headers={
                "Location": "http://127.0.0.1:8000/tasks/task-id",
                "Retry-After": "0",
            },
        )
        task_response = _server_response(
            200,
            url="http://127.0.0.1:8000/tasks/task-id",
            json_data=task,
        )
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=submit_response)
        mock_client.get = AsyncMock(return_value=task_response)
        app.state.http_client = mock_client

        transport = httpx.ASGITransport(app=app)
        async with RealAsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/frontend/explain/",
                json={"prompt": "https://example.com/build.log"},
            )

        assert resp.status_code == 502
        assert task["status"] == status
        assert expected_detail in resp.json()["description"]

    @patch("src.api._check_log_urls", new_callable=AsyncMock)
    @patch("src.api._download_log_content", new_callable=AsyncMock)
    async def test_explain_server_timeout(self, mock_download, _mock_check):
        mock_download.return_value = FAKE_LOG_CONTENT

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ReadTimeout("read timed out"))
        app.state.http_client = mock_client

        transport = httpx.ASGITransport(app=app)
        async with RealAsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/frontend/explain/",
                json={"prompt": "https://example.com/build.log"},
            )

        assert resp.status_code == 504

    @patch("src.api._check_log_urls", new_callable=AsyncMock)
    @patch("src.api._download_log_content", new_callable=AsyncMock)
    async def test_explain_server_connect_error(self, mock_download, _mock_check):
        mock_download.return_value = FAKE_LOG_CONTENT

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.ConnectError("connection refused")
        )
        app.state.http_client = mock_client

        transport = httpx.ASGITransport(app=app)
        async with RealAsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/frontend/explain/",
                json={"prompt": "https://example.com/build.log"},
            )

        assert resp.status_code == 502

    @patch("src.api._check_log_urls", new_callable=AsyncMock)
    @patch("src.api._download_log_content", new_callable=AsyncMock)
    async def test_explain_server_500(self, mock_download, _mock_check):
        mock_download.return_value = FAKE_LOG_CONTENT

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
            resp = await client.post(
                "/frontend/explain/",
                json={"prompt": "https://example.com/build.log"},
            )

        assert resp.status_code == 500


class TestExplainProviderEndpoints:
    """Tests for provider-specific explain endpoints."""

    @patch("src.api._call_analyze_api", new_callable=AsyncMock)
    @patch("src.api.CoprProvider")
    async def test_explain_copr(self, mock_cls, mock_analyze):
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

    @patch("src.api._call_analyze_api", new_callable=AsyncMock)
    @patch("src.api.KojiProvider")
    async def test_explain_koji(self, mock_cls, mock_analyze):
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

    @patch("src.api._call_analyze_api", new_callable=AsyncMock)
    @patch("src.api.PackitProvider")
    async def test_explain_packit(self, mock_cls, mock_analyze):
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

    @patch("src.api._call_analyze_api", new_callable=AsyncMock)
    @patch("src.api.URLProvider")
    async def test_explain_url(self, mock_cls, mock_analyze):
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

    @patch("src.api._call_analyze_api", new_callable=AsyncMock)
    @patch("src.api.ContainerProvider")
    async def test_explain_container(self, mock_cls, mock_analyze):
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

    @patch("src.api._call_analyze_api", new_callable=AsyncMock)
    @patch("src.api.OBSProvider")
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

    @patch("src.api._check_log_urls", new_callable=AsyncMock)
    @patch("src.api.CoprProvider")
    async def test_explain_provider_timeout(self, mock_cls, _mock_check):
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

    @patch("src.api._check_log_urls", new_callable=AsyncMock)
    @patch("src.api.CoprProvider")
    async def test_explain_provider_server_error(self, mock_cls, _mock_check):
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


class TestCheckLogUrls:
    """Tests for _check_log_urls."""

    async def test_all_reachable(self):
        from src.api import _check_log_urls

        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.head = AsyncMock(return_value=mock_response)

        await _check_log_urls(
            [
                {"name": "build.log", "url": "https://example.com/build.log"},
                {"name": "root.log", "url": "https://example.com/root.log"},
            ],
            http_client=mock_client,
        )

    async def test_unreachable_url_returns_404(self):
        from src.api import _check_log_urls

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = AsyncMock()
        mock_client.head = AsyncMock(return_value=mock_response)

        with pytest.raises(HTTPException) as exc_info:
            await _check_log_urls(
                [
                    {"name": "build.log", "url": "https://example.com/missing.log"},
                ],
                http_client=mock_client,
            )
        assert exc_info.value.status_code == 422
        assert "missing.log" in exc_info.value.detail

    async def test_unreachable_url_connection_error(self):
        from src.api import _check_log_urls

        mock_client = AsyncMock()
        mock_client.head = AsyncMock(
            side_effect=httpx.ConnectError("connection refused")
        )

        with pytest.raises(HTTPException) as exc_info:
            await _check_log_urls(
                [
                    {"name": "build.log", "url": "https://example.com/build.log"},
                ],
                http_client=mock_client,
            )
        assert exc_info.value.status_code == 422
        assert "connection refused" in exc_info.value.detail


class TestDownloadEndpoint:
    """Tests for the /download endpoint - with and without `since` parameter."""

    def test_download_serves_prebuilt_archive(self, tmp_path, monkeypatch):
        """Test that the /download endpoint serves a prebuilt archive if it exists.
        Archives sit in the parent of FEEDBACK_DIR (i.e. /persistent/)"""

        results_dir = str(tmp_path / "results")
        monkeypatch.setattr("src.api.FEEDBACK_DIR", results_dir)
        archive = tmp_path / "results-2026-07-14.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            dummy = tmp_path / "dummy.txt"
            dummy.write_text("hello")
            tar.add(dummy, arcname="results/results/dummy.txt")

        client = TestClient(app)
        resp = client.get("/download")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/x-tar"

    def test_download_no_archive_returns_404(self, tmp_path, monkeypatch):
        """Return 404 for /download if no archive exists."""

        results_dir = tmp_path / "results"
        results_dir.mkdir()
        monkeypatch.setattr("src.api.FEEDBACK_DIR", str(results_dir))

        client = TestClient(app)
        resp = client.get("/download")
        assert resp.status_code == 404

    @patch("src.api.date")
    def test_download_since_returns_filtered_archive(
        self, mock_date, tmp_path, monkeypatch
    ):
        """Return a filtered archive for /download?since=<date> and valid date."""

        mock_date.today.return_value = date(2026, 7, 15)
        mock_date.fromisoformat = date.fromisoformat

        results_dir = tmp_path / "results"
        (results_dir / "2026-07-10" / "copr" / "123").mkdir(parents=True)
        (results_dir / "2026-07-10" / "copr" / "123" / "a.json").write_text("{}")
        (results_dir / "2026-07-12" / "copr" / "456").mkdir(parents=True)
        (results_dir / "2026-07-12" / "copr" / "456" / "b.json").write_text("{}")
        (results_dir / "2026-07-05" / "koji" / "789").mkdir(parents=True)
        (results_dir / "2026-07-05" / "koji" / "789" / "c.json").write_text("{}")
        monkeypatch.setattr("src.api.FEEDBACK_DIR", str(results_dir))

        client = TestClient(app)
        resp = client.get("/download", params={"since": "2026-07-10"})
        assert resp.status_code == 200

        archive_path = tmp_path / "response.tar.gz"
        archive_path.write_bytes(resp.content)
        with tarfile.open(archive_path, "r:gz") as tar:
            names = tar.getnames()
        assert any("2026-07-10" in n for n in names)
        assert any("2026-07-12" in n for n in names)
        assert not any("2026-07-05" in n for n in names)

    @patch("src.api.date")
    def test_download_since_includes_boundary_date(
        self, mock_date, tmp_path, monkeypatch
    ):
        """Make sure that results from `since` date are included."""

        mock_date.today.return_value = date(2026, 7, 15)
        mock_date.fromisoformat = date.fromisoformat

        results_dir = tmp_path / "results"
        (results_dir / "2026-07-10" / "copr" / "123").mkdir(parents=True)
        (results_dir / "2026-07-10" / "copr" / "123" / "a.json").write_text("{}")
        (results_dir / "2026-07-09" / "copr" / "456").mkdir(parents=True)
        (results_dir / "2026-07-09" / "copr" / "456" / "b.json").write_text("{}")
        monkeypatch.setattr("src.api.FEEDBACK_DIR", str(results_dir))

        client = TestClient(app)
        resp = client.get("/download", params={"since": "2026-07-10"})
        assert resp.status_code == 200

        archive_path = tmp_path / "response.tar.gz"
        archive_path.write_bytes(resp.content)
        with tarfile.open(archive_path, "r:gz") as tar:
            names = tar.getnames()
        assert any("2026-07-10" in n for n in names)
        assert not any("2026-07-09" in n for n in names)

    @patch("src.api.date")
    def test_download_since_skips_empty_and_non_json_dirs(
        self, mock_date, tmp_path, monkeypatch
    ):
        """Return 204 when matching date dirs exist but contain no JSON files."""

        mock_date.today.return_value = date(2026, 7, 15)
        mock_date.fromisoformat = date.fromisoformat

        results_dir = tmp_path / "results"
        # Empty directory
        (results_dir / "2026-07-10").mkdir(parents=True)
        # Directory with only non-JSON files
        (results_dir / "2026-07-11" / "copr" / "123").mkdir(parents=True)
        (results_dir / "2026-07-11" / "copr" / "123" / "notes.txt").write_text("hello")
        monkeypatch.setattr("src.api.FEEDBACK_DIR", str(results_dir))

        client = TestClient(app)
        resp = client.get("/download", params={"since": "2026-07-10"})
        assert resp.status_code == 204

    @patch("src.api.date")
    def test_download_since_empty_returns_204(self, mock_date, tmp_path, monkeypatch):
        """Return 204 for /download?since=<date> if no results exist since that date.
        This also applies if the date is in the future."""

        mock_date.today.return_value = date(2026, 7, 15)
        mock_date.fromisoformat = date.fromisoformat

        results_dir = tmp_path / "results"
        (results_dir / "2026-07-01" / "copr" / "123").mkdir(parents=True)
        (results_dir / "2026-07-01" / "copr" / "123" / "a.json").write_text("{}")
        monkeypatch.setattr("src.api.FEEDBACK_DIR", str(results_dir))

        client = TestClient(app)
        resp = client.get("/download", params={"since": "2099-01-01"})
        assert resp.status_code == 204

    def test_download_since_invalid_date_returns_422(self, tmp_path, monkeypatch):
        """Return 422 for /download?since=<date> if the date is invalid."""

        monkeypatch.setattr("src.api.FEEDBACK_DIR", str(tmp_path / "results"))

        client = TestClient(app)
        resp = client.get("/download", params={"since": "not-a-date"})
        assert resp.status_code == 422

    def test_download_since_too_old_returns_400(self, tmp_path, monkeypatch):
        """Return 400 if the since date is older than DOWNLOAD_SINCE_MAX_DAYS."""

        monkeypatch.setattr("src.api.FEEDBACK_DIR", str(tmp_path / "results"))

        client = TestClient(app)
        resp = client.get("/download", params={"since": "2020-01-01"})
        assert resp.status_code == 400
        assert "The 'since' date must be within" in resp.json()["description"]


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
