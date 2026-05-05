import binascii
import subprocess
from http import HTTPStatus
from unittest.mock import patch

import copr.v3
import httpx
import koji
import pytest
from fastapi import HTTPException

from src.fetcher import handle_errors


class TestHandleErrorsAsync:
    async def test_httpx_status_error(self):
        @handle_errors
        async def failing():
            response = httpx.Response(
                502,
                request=httpx.Request("GET", "https://example.com/log"),
            )
            raise httpx.HTTPStatusError(
                "Bad Gateway", request=response.request, response=response
            )

        with pytest.raises(HTTPException) as exc_info:
            await failing()
        assert exc_info.value.status_code == 502
        assert "502" in exc_info.value.detail
        assert "example.com/log" in exc_info.value.detail

    async def test_copr_no_result_exception(self):
        @handle_errors
        async def failing():
            raise copr.v3.exceptions.CoprNoResultException("build not found")

        with pytest.raises(HTTPException) as exc_info:
            await failing()
        assert exc_info.value.status_code == HTTPStatus.BAD_REQUEST
        assert "build not found" in exc_info.value.detail

    async def test_koji_generic_error(self):
        @handle_errors
        async def failing():
            raise koji.GenericError("invalid task")

        with pytest.raises(HTTPException) as exc_info:
            await failing()
        assert exc_info.value.status_code == HTTPStatus.BAD_REQUEST
        assert "invalid task" in exc_info.value.detail

    async def test_binascii_error(self):
        @handle_errors
        async def failing():
            raise binascii.Error("Invalid base64")

        with pytest.raises(HTTPException) as exc_info:
            await failing()
        assert exc_info.value.status_code == HTTPStatus.NOT_FOUND
        assert "base64" in exc_info.value.detail

    async def test_called_process_error_no_such_task(self):
        @handle_errors
        async def failing():
            raise subprocess.CalledProcessError(
                1, "cmd", output=b"", stderr=b"No such task: 999"
            )

        with pytest.raises(HTTPException) as exc_info:
            await failing()
        assert exc_info.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert "No such task" in exc_info.value.detail

    @patch.dict("os.environ", {"ENV": "devel"})
    async def test_called_process_error_non_production(self):
        @handle_errors
        async def failing():
            raise subprocess.CalledProcessError(1, "cmd", output=b"out", stderr=b"err")

        with pytest.raises(HTTPException) as exc_info:
            await failing()
        assert exc_info.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert "stdout" in exc_info.value.detail
        assert "stderr" in exc_info.value.detail

    @patch.dict("os.environ", {"ENV": "production"})
    async def test_called_process_error_production(self):
        @handle_errors
        async def failing():
            raise subprocess.CalledProcessError(1, "cmd", output=b"out", stderr=b"err")

        with pytest.raises(HTTPException) as exc_info:
            await failing()
        assert exc_info.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Internal Server Error"

    async def test_http_exception_passthrough(self):
        @handle_errors
        async def failing():
            raise HTTPException(status_code=418, detail="I'm a teapot")

        with pytest.raises(HTTPException) as exc_info:
            await failing()
        assert exc_info.value.status_code == 418
        assert exc_info.value.detail == "I'm a teapot"

    async def test_unknown_exception_reraised(self):
        @handle_errors
        async def failing():
            raise RuntimeError("unexpected")

        with pytest.raises(RuntimeError, match="unexpected"):
            await failing()

    async def test_success_returns_value(self):
        @handle_errors
        async def succeeding():
            return "ok"

        assert await succeeding() == "ok"


class TestHandleErrorsSync:
    def test_binascii_error(self):
        @handle_errors
        def failing():
            raise binascii.Error("bad input")

        with pytest.raises(HTTPException) as exc_info:
            failing()
        assert exc_info.value.status_code == HTTPStatus.NOT_FOUND

    def test_koji_generic_error(self):
        @handle_errors
        def failing():
            raise koji.GenericError("bad task")

        with pytest.raises(HTTPException) as exc_info:
            failing()
        assert exc_info.value.status_code == HTTPStatus.BAD_REQUEST

    def test_success_returns_value(self):
        @handle_errors
        def succeeding():
            return 42

        assert succeeding() == 42

    def test_unknown_exception_reraised(self):
        @handle_errors
        def failing():
            raise ValueError("nope")

        with pytest.raises(ValueError, match="nope"):
            failing()
