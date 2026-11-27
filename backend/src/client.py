"""Application-owned remote resource and analysis service clients."""

from asyncio import timeout
from contextlib import asynccontextmanager
from urllib.parse import urlunsplit

import aiohttp
import httpx
from aiohttp.payload import BytesPayload
from yarl import URL

from src.constants import (
    LOGDETECTIVE_CONNECT_TIMEOUT,
    LOGDETECTIVE_DEFAULT_TIMEOUT,
    LOGDETECTIVE_MAX_CONNECTION_LIMIT,
    LOGDETECTIVE_MAX_KEEPALIVE_CONNECTIONS,
    LOGDETECTIVE_READ_TIMEOUT,
    SERVER_URL,
)
from src.ssrf import SSRFProtectedConnector


def remote_timeout(seconds: float) -> aiohttp.ClientTimeout:
    """Limit connection and read inactivity, not total transfer time."""
    return aiohttp.ClientTimeout(connect=seconds, sock_read=seconds)


def validate_url(url: URL) -> None:
    """Check credentials before aiohttp turns URL userinfo into Authorization."""
    if (
        url.scheme not in ("http", "https")
        or not url.raw_host
        or url.raw_user is not None
        or url.raw_password is not None
    ):
        raise aiohttp.InvalidURL("Remote log URLs must use HTTP(S) without credentials")


async def _validate_start(_session, _context, params):
    validate_url(params.url)


def wire_url(value: str) -> URL:
    """Encode an IRI's host and unescaped text without normalizing existing escapes."""
    try:
        return URL(str(httpx.URL(value)), encoded=True)
    except (httpx.InvalidURL, ValueError) as exc:
        raise aiohttp.InvalidURL(str(exc)) from exc


def _resolve_reference(base: URL, value: str) -> URL:
    """Merge raw components so neither escaped slashes nor empty segments are lost."""
    reference = wire_url(value)
    if reference.scheme != "":
        return reference
    if reference.raw_authority != "":
        return reference.with_scheme(base.scheme)
    path = reference.raw_path
    query = reference.raw_query_string
    if not path:
        path = base.raw_path
        if not value or value.startswith("#"):
            query = base.raw_query_string
    elif not path.startswith("/"):
        directory, _, _ = base.raw_path.rpartition("/")
        path = f"{directory}/{path}"
    # HTTPX removes dot segments from an absolute path without decoding escapes.
    return wire_url(
        urlunsplit(
            (base.scheme, base.raw_authority, path, query, reference.raw_fragment)
        )
    )


def _prepare_target(value: str, base: URL | None = None) -> URL:
    """Resolve before validation: Yarl may parse the port on first host access."""
    try:
        target = wire_url(value) if base is None else _resolve_reference(base, value)
        validate_url(target)
    except aiohttp.InvalidURL:
        raise
    except ValueError as exc:
        raise aiohttp.InvalidURL(str(exc)) from exc
    return target


class RemoteResourceClient:
    """Follow GET and HEAD redirects without rewriting signed request targets."""

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    def get(self, url: str, **kwargs):
        """Open a streaming GET response."""
        return self.request("GET", url, **kwargs)

    def head(self, url: str, **kwargs):
        """Check a resource without downloading its body."""
        return self.request("HEAD", url, **kwargs)

    @asynccontextmanager
    async def request(self, method: str, url: str, **kwargs):
        """Validate and release each redirect before requesting the next URL."""
        target = _prepare_target(url)
        history = []
        while True:
            async with self.session.request(
                method, target, allow_redirects=False, **kwargs
            ) as response:
                if response.status in (301, 302, 303, 307, 308):
                    history.append(response)
                    if len(history) >= 10:
                        raise aiohttp.TooManyRedirects(
                            history[0].request_info, tuple(history)
                        )
                    location = response.headers.get("Location") or response.headers.get(
                        "URI"
                    )
                    if location is not None:
                        target = _prepare_target(location, target)
                        continue
                yield response
                return


class _ServiceClient(httpx.AsyncClient):
    """Own HTTPX's directly connected and environment-proxy transports."""

    async def send_hop(self, request: httpx.Request) -> httpx.Response:
        """Send once; the outer analysis client handles cookies, logging and redirects."""
        return await self._transport_for_url(request.url).handle_async_request(request)


class _TimedUpload(BytesPayload):
    """Apply the HTTPX write deadline only while aiohttp sends the request body."""

    def __init__(self, data: bytes, write_timeout: float | None):
        super().__init__(data)
        self.write_timeout = write_timeout

    async def write(self, writer):
        """Write a complete body with aiohttp 3.10."""
        await self.write_with_length(writer, None)

    async def write_with_length(self, writer, content_length):
        """Respect the length limit passed by newer aiohttp releases."""
        async with timeout(self.write_timeout):
            await writer.write(self._value[:content_length])


class _AnalysisTransport(httpx.AsyncBaseTransport):
    """Let HTTPX route each redirect; delegate exactly one untrusted hop."""

    def __init__(self, remote: aiohttp.ClientSession, service: _ServiceClient):
        self.service = service
        self.server = httpx.URL(SERVER_URL)
        self.remote = remote

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        if not url.userinfo and (url.scheme, url.raw_host, url.port) == (
            self.server.scheme,
            self.server.raw_host,
            self.server.port,
        ):
            return await self.service.send_hop(request)
        # Polling a task Location is a new GET, not an HTTPX redirect. Never
        # forward analysis-service credentials to a different origin.
        headers = request.headers.copy()
        headers.pop("Authorization", None)
        headers.pop("Cookie", None)
        limits = request.extensions.get("timeout", {})
        try:
            body = await request.aread()
            async with self.remote.request(
                request.method,
                URL(str(url), encoded=True),
                headers=headers.multi_items(),
                data=_TimedUpload(body, limits.get("write")) if body else None,
                allow_redirects=False,
                auto_decompress=False,
                timeout=aiohttp.ClientTimeout(
                    connect=limits.get("connect"), sock_read=limits.get("read")
                ),
            ) as response:
                return httpx.Response(
                    response.status,
                    # HTTPX extracts cookies from transport responses into its
                    # shared jar. Only the configured service may set them.
                    headers=[
                        (name, value)
                        for name, value in response.raw_headers
                        if name.lower() != b"set-cookie"
                    ],
                    content=await response.read(),
                )
        except TimeoutError as exc:
            raise httpx.TimeoutException(str(exc), request=request) from exc
        except (aiohttp.ClientError, ValueError) as exc:
            raise httpx.ConnectError(str(exc), request=request) from exc


@asynccontextmanager
async def application_clients():
    """Keep both clients alive until FastAPI shuts down."""
    trace = aiohttp.TraceConfig()
    trace.on_request_start.append(_validate_start)
    async with (
        aiohttp.ClientSession(
            connector=SSRFProtectedConnector(),
            trust_env=False,
            cookie_jar=aiohttp.DummyCookieJar(),
            trace_configs=[trace],
            timeout=aiohttp.ClientTimeout(
                connect=LOGDETECTIVE_CONNECT_TIMEOUT,
                sock_read=LOGDETECTIVE_READ_TIMEOUT,
            ),
        ) as remote,
        _ServiceClient(
            limits=httpx.Limits(
                max_connections=LOGDETECTIVE_MAX_CONNECTION_LIMIT,
                max_keepalive_connections=LOGDETECTIVE_MAX_KEEPALIVE_CONNECTIONS,
            ),
        ) as service,
        httpx.AsyncClient(
            transport=_AnalysisTransport(remote, service),
            follow_redirects=True,
            timeout=httpx.Timeout(
                LOGDETECTIVE_DEFAULT_TIMEOUT,
                connect=LOGDETECTIVE_CONNECT_TIMEOUT,
                read=LOGDETECTIVE_READ_TIMEOUT,
            ),
        ) as analysis,
    ):
        yield RemoteResourceClient(remote), analysis
