"""
HTTP client utility module
"""

from httpx import AsyncClient, Limits, Timeout

from src.constants import (
    LOGDETECTIVE_CONNECT_TIMEOUT,
    LOGDETECTIVE_DEFAULT_TIMEOUT,
    LOGDETECTIVE_MAX_CONNECTION_LIMIT,
    LOGDETECTIVE_MAX_KEEPALIVE_CONNECTIONS,
    LOGDETECTIVE_READ_TIMEOUT,
)


def get_http_client() -> AsyncClient:
    """Create a new httpx.AsyncClient with application-wide defaults."""
    return AsyncClient(
        timeout=Timeout(
            LOGDETECTIVE_DEFAULT_TIMEOUT,
            connect=LOGDETECTIVE_CONNECT_TIMEOUT,
            read=LOGDETECTIVE_READ_TIMEOUT,
        ),
        follow_redirects=True,
        limits=Limits(
            max_connections=LOGDETECTIVE_MAX_CONNECTION_LIMIT,
            max_keepalive_connections=LOGDETECTIVE_MAX_KEEPALIVE_CONNECTIONS,
        ),
    )
