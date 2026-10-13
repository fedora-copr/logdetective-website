"""
Test the API /explain endpoints.
"""

# Endpoint cases keep their setup local for readability.
# pylint: disable=duplicate-code

from unittest.mock import AsyncMock, call, patch

import httpx
import pytest

from src.api import app
from src.constants import LOGDETECTIVE_READ_TIMEOUT


@pytest.fixture(autouse=True)
def _mock_sleep():
    """Ensure app.state.http_client exists for tests that bypass lifespan."""
    with patch("src.analysis.sleep", new_callable=AsyncMock):
        yield


FAKE_LOG_CONTENT = "mock build log content"

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


class TestExplainEndpoint:
    """Tests for the direct-log explain endpoint."""

    @patch("src.analysis._poll_for_analysis_task", new_callable=AsyncMock)
    @patch("src.analysis._check_log_urls", new_callable=AsyncMock)
    @patch("src.api_explain._download_log_content", new_callable=AsyncMock)
    async def test_explain_success(self, mock_download, _mock_check, mock_poll):
        """Return an explanation and downloaded logs on success."""
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

    @patch("src.analysis._check_log_urls", new_callable=AsyncMock)
    @patch("src.api_explain._download_log_content", new_callable=AsyncMock)
    @patch("src.analysis.sleep", new_callable=AsyncMock)
    async def test_explain_polls_until_task_is_done(
        self, mock_sleep, mock_download, _mock_check
    ):
        """Poll the analysis task until it returns a completed result."""
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

    @patch("src.analysis._check_log_urls", new_callable=AsyncMock)
    @patch("src.api_explain._download_log_content", new_callable=AsyncMock)
    async def test_explain_submission_missing_location(
        self, mock_download, _mock_check
    ):
        """Return an error when task submission omits its location."""
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
    @patch("src.analysis._check_log_urls", new_callable=AsyncMock)
    @patch("src.api_explain._download_log_content", new_callable=AsyncMock)
    async def test_explain_result_validation(
        self, mock_download, _mock_check, result, expected_status
    ):
        """Reject malformed analysis results."""
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
    @patch("src.analysis._check_log_urls", new_callable=AsyncMock)
    @patch("src.api_explain._download_log_content", new_callable=AsyncMock)
    async def test_explain_polling_get_failure(
        self, mock_download, _mock_check, failure, expected_status
    ):
        """Translate polling failures into the expected HTTP status."""
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

    @patch("src.analysis._poll_for_analysis_task", new_callable=AsyncMock)
    @patch("src.analysis._check_log_urls", new_callable=AsyncMock)
    @patch("src.api_explain._download_log_content", new_callable=AsyncMock)
    async def test_explain_polling_timeout(self, mock_download, _mock_check, mock_poll):
        """Return a gateway timeout when polling exceeds its time limit."""
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

    @patch("src.analysis.LOG_DETECTIVE_TOKEN", "test-token")
    @patch("src.analysis._poll_for_analysis_task", new_callable=AsyncMock)
    @patch("src.analysis._check_log_urls", new_callable=AsyncMock)
    @patch("src.api_explain._download_log_content", new_callable=AsyncMock)
    async def test_explain_forwards_authorization_on_submission_and_poll(
        self, mock_download, _mock_check, mock_poll
    ):
        """Forward authorization to the analysis service for both requests."""
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
    @patch("src.analysis._check_log_urls", new_callable=AsyncMock)
    @patch("src.api_explain._download_log_content", new_callable=AsyncMock)
    async def test_explain_terminal_task_failure(
        self,
        mock_download,
        _mock_check,
        status,
        task,
        expected_detail,
    ):
        """Return an error when an analysis task fails or is cancelled."""
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

    @patch("src.analysis._check_log_urls", new_callable=AsyncMock)
    @patch("src.api_explain._download_log_content", new_callable=AsyncMock)
    async def test_explain_server_timeout(self, mock_download, _mock_check):
        """Translate an analysis server timeout into a gateway timeout."""
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

    @patch("src.analysis._check_log_urls", new_callable=AsyncMock)
    @patch("src.api_explain._download_log_content", new_callable=AsyncMock)
    async def test_explain_server_connect_error(self, mock_download, _mock_check):
        """Translate an analysis server connection error."""
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

    @patch("src.analysis._check_log_urls", new_callable=AsyncMock)
    @patch("src.api_explain._download_log_content", new_callable=AsyncMock)
    async def test_explain_server_500(self, mock_download, _mock_check):
        """Return the analysis server's error status."""
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
