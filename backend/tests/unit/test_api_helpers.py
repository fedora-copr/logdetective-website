"""
Test the API helper functions.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from starlette.exceptions import HTTPException

from src.analysis import _check_log_urls


class TestCheckLogUrls:
    """Tests for _check_log_urls."""

    async def test_all_reachable(self):
        """Accept a set of reachable log URLs."""
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
        """Reject log URLs that return a not-found response."""
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
        """Reject log URLs when the connection fails."""
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
