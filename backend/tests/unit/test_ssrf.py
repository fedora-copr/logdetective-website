"""Regression tests for public-only remote log requests."""

import asyncio
import gzip
import socket
import zlib
from contextlib import asynccontextmanager
from ssl import CERT_REQUIRED, SSLCertVerificationError
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import httpx
import pytest
from fastapi import HTTPException

from src.analysis import _call_analyze_api, _check_log_urls, _download_log_content
from src.api import app
from src.client import application_clients, remote_timeout
from src.constants import SERVER_URL
from src.exceptions import MaximumArtifactSizeExceeded
from src.fetcher import KojiProvider
from src.spells import fetch_text
from src.ssrf import SSRFProtectedResolver


def dns_answer(address):
    """Build a getaddrinfo answer for either IP family."""
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    return (
        family,
        socket.SOCK_STREAM,
        6,
        "",
        ((address, 443, 0, 0) if family == socket.AF_INET6 else (address, 443)),
    )


@pytest.fixture
async def no_tcp_connections():
    """Fail if a rejected request attempts to open a socket."""
    with patch.object(
        asyncio.get_running_loop(),
        "sock_connect",
        side_effect=AssertionError("Rejected destination reached TCP"),
    ) as connect:
        yield
        connect.assert_not_awaited()


def redirect_location(path, port):
    """Return the Location header for the fixture's redirect routes."""
    if path.startswith("/signed/") and "/sub/" in path:
        return "../next//my build%32?key=%33&key=%2b"
    if path.startswith("/bad-port/"):
        return f"http://8.8.8.8:{path.split('/')[-1]}/log"
    if path.startswith("/redirect/"):
        return f"/{path.removeprefix('/redirect/')}"
    if path in ("/private", "/credentials"):
        target = "127.0.0.1" if path == "/private" else "user:pass@8.8.8.8"
        return f"http://{target}:{port}/log"
    if path == "/clear-query?previous=value":
        return "?"
    return None


@asynccontextmanager
async def resource_server(monkeypatch):
    """Route validated public fixture addresses to a controlled test server."""
    calls = []

    async def serve(reader, writer):
        try:
            headers = await reader.readuntil(b"\r\n\r\n")
            method, path, _ = headers.split(b"\r\n", 1)[0].decode().split()
            calls.append((method, path))
            status, extra, body = "200 OK", "", b""
            location = redirect_location(path, port)
            if location is not None:
                status, extra = "302 Found", f"Location: {location}\r\n"
            elif path.partition("?")[0] == "/task":
                assert b"authorization:" not in headers.lower()
                assert b"cookie:" not in headers.lower()
                body = gzip.compress(
                    b'{"status":"done","result":{"explanation":"done"}}'
                )
                extra = (
                    "Content-Encoding: gzip\r\n"
                    "Set-Cookie: task=untrusted; Path=/\r\n"
                    "sEt-CoOkIe: second=untrusted; Path=/\r\n"
                )
            elif path == "/stacked":
                extra = "Content-Encoding: gzip, deflate\r\n"
                body = zlib.compress(gzip.compress(b"text"))
            elif path == "/upload":
                if not await reader.read(4):
                    return  # The client cancelled the stalled upload.
            elif path == "/broken":
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 99\r\n\r\npartial")
                await writer.drain()
                return
            elif path == "/fixture.src.rpm":
                body = b"\xed\xab\xee\xdb\x00\xff"
            elif path == "/no-location":
                status = "302 Found"
            elif path == "/missing":
                status = "404 Not Found"
            else:
                extra = "Content-Encoding: gzip\r\n"
                body = gzip.compress(
                    b"x" * (1024 if path == "/large" else 1023) + b"\xff"
                )
            writer.write(
                f"HTTP/1.1 {status}\r\n{extra}Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n".encode()
            )
            if method != "HEAD":
                writer.write(body)
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    loop = asyncio.get_running_loop()
    connect = loop.sock_connect

    async def local_connect(sock, address):
        assert address == ("8.8.8.8", port)
        return await connect(sock, ("127.0.0.1", port))

    monkeypatch.setattr(loop, "sock_connect", local_connect)
    async with server, application_clients() as (remote, analysis):
        yield f"http://8.8.8.8:{port}", calls, remote, analysis


class TestSSRFAndRedirects:  # pylint: disable=too-many-public-methods
    """Verify destination checks, redirects, and downloads through the application clients."""

    async def test_lifespan_owns_both_clients(self):
        """Requests reuse the two clients until the application shuts down."""
        with patch("src.api.Storator3000.ensure_directories"):
            async with app.router.lifespan_context(app):
                remote = app.state.http_client
                analysis = app.state.analysis_client
                assert remote is not analysis
                assert not remote.session.closed and not analysis.is_closed
        assert remote.session.closed and analysis.is_closed

    @pytest.mark.parametrize(
        "address",
        [
            "127.0.0.1",
            "10.0.0.1",
            "172.30.0.1",
            "192.168.0.1",
            "169.254.169.254",
            "0.0.0.0",
            "100.100.100.200",
            "224.0.0.1",
            "240.0.0.1",
            "192.0.2.1",
            "::",
            "::1",
            "fc00::1",
            "fe80::1",
            "fec0::1",
            "ff02::1",
            "2001:db8::1",
            "::ffff:127.0.0.1",
            "::ffff:10.0.0.1",
        ],
    )
    async def test_forbidden_answers(self, address):
        """Reject unsafe literals and mixed answer sets before connecting."""
        resolver = SSRFProtectedResolver()
        for answers in (
            [dns_answer(address)],
            [dns_answer("8.8.8.8"), dns_answer(address)],
        ):
            with (
                patch.object(
                    asyncio.get_running_loop(), "getaddrinfo", return_value=answers
                ),
                pytest.raises(OSError, match="forbidden"),
            ):
                await resolver.resolve("logs.example")

    @pytest.mark.parametrize(
        "host", ["127.0.0.1", "2130706433", "0x7f000001", "[::1]", "[fec0::1]"]
    )
    @pytest.mark.usefixtures("no_tcp_connections")
    async def test_real_literal_resolution(self, host):
        """Exercise system parsing of standard and alternative numeric IP spellings."""
        async with application_clients() as (client, _):
            with pytest.raises(aiohttp.ClientError):
                async with client.get(f"http://{host}/log"):
                    pytest.fail("Unexpected successful request")

    @pytest.mark.parametrize(
        "url",
        [
            "ftp://logs.example/log",
            "http://user:pass@logs.example/log",
            "http://[fe80::1%25eth0]/log",
        ],
    )
    async def test_invalid_destination(self, url):
        """Reject unsupported schemes, credentials and zone identifiers."""
        async with application_clients() as (client, _):
            with pytest.raises(aiohttp.ClientError):
                async with client.get(url):
                    pytest.fail("Unexpected successful request")

    async def test_empty_or_failed_dns(self):
        """DNS failure and empty answers fail closed."""
        for value in ([], socket.gaierror("no answer")):
            mock = (
                AsyncMock(side_effect=value)
                if isinstance(value, Exception)
                else AsyncMock(return_value=value)
            )
            with (
                patch.object(asyncio.get_running_loop(), "getaddrinfo", mock),
                pytest.raises(OSError),
            ):
                await SSRFProtectedResolver().resolve("logs.example")

    @pytest.mark.usefixtures("no_tcp_connections")
    async def test_unicode_host_with_mixed_answers_is_rejected(self):
        """Validate the same IDNA hostname that aiohttp will send on the wire."""
        with (
            patch.object(
                asyncio.get_running_loop(),
                "getaddrinfo",
                return_value=[dns_answer("8.8.8.8"), dns_answer("127.0.0.1")],
            ) as dns,
        ):
            async with application_clients() as (client, _):
                with pytest.raises(aiohttp.ClientError, match="forbidden"):
                    async with client.get("https://faß.example/log"):
                        pytest.fail("Unexpected successful request")
        assert dns.await_args.args == ("xn--fa-hia.example", 443)

    @pytest.mark.parametrize("stall", [False, True])
    async def test_all_tcp_attempts_fail(self, stall):
        """Unreachable addresses surface a connection error or a shared timeout."""

        async def unreachable(*_args, **_kwargs):
            if stall:
                await asyncio.Event().wait()
            raise OSError(101, "unreachable")

        with (
            patch.object(
                asyncio.get_running_loop(),
                "getaddrinfo",
                return_value=[dns_answer("8.8.8.8"), dns_answer("1.1.1.1")],
            ),
            patch.object(
                asyncio.get_running_loop(), "sock_connect", side_effect=unreachable
            ) as tcp,
        ):
            async with application_clients() as (client, _):
                with pytest.raises(
                    TimeoutError if stall else aiohttp.ClientConnectionError
                ):
                    async with client.get(
                        "https://logs.example/log",
                        timeout=remote_timeout(0.1 if stall else 5),
                    ):
                        pytest.fail("Unexpected successful request")
        assert {call.args[1][0] for call in tcp.await_args_list} == (
            {"8.8.8.8"} if stall else {"8.8.8.8", "1.1.1.1"}
        )

    async def test_lookup_timeout(self):
        """Bound DNS lookup by the configured connection timeout."""

        async def slow_resolve(*_args, **_kwargs):
            await asyncio.sleep(1)

        with patch.object(SSRFProtectedResolver, "resolve", slow_resolve):
            async with application_clients() as (client, _):
                with pytest.raises(TimeoutError):
                    async with client.get(
                        "https://logs.example/log", timeout=remote_timeout(0.001)
                    ):
                        pytest.fail("Unexpected successful request")

    @pytest.mark.usefixtures("no_tcp_connections")
    async def test_forbidden_url_in_download_and_head(self):
        """Both reachable entry paths reject private URLs without outbound traffic."""
        async with application_clients() as (client, _):
            with pytest.raises(HTTPException) as download:
                await _download_log_content("http://127.0.0.1/secret", client=client)
            assert download.value.status_code == 502
            with pytest.raises(HTTPException) as check:
                await _check_log_urls(
                    [{"name": "secret", "url": "http://127.0.0.1/secret"}],
                    http_client=client,
                )
            assert check.value.status_code == 422

    @pytest.mark.parametrize(
        ("server_url", "server_address"),
        [
            ("http://127.0.0.1:8000", "127.0.0.1"),
            ("https://analysis.internal", "10.0.0.1"),
            ("http://[::1]:8000", "::1"),
        ],
    )
    async def test_analysis_uses_configured_private_origin(
        self, monkeypatch, server_url, server_address
    ):
        """Only service requests can connect to the configured private origin."""
        monkeypatch.setattr("src.analysis.SERVER_URL", server_url)
        monkeypatch.setattr("src.client.SERVER_URL", server_url)
        log_url = "https://logs.example/build.log"
        server = httpx.URL(server_url)

        async def lookup(host, _port, **options):
            assert options["type"] == socket.SOCK_STREAM
            return [dns_answer("8.8.8.8" if host == "logs.example" else server_address)]

        with (
            patch.object(asyncio.get_running_loop(), "getaddrinfo", side_effect=lookup),
            patch.object(
                httpx.AsyncHTTPTransport,
                "handle_async_request",
                side_effect=[
                    httpx.Response(
                        202,
                        headers={
                            "Location": f"{server_url}/tasks/1",
                            "Retry-After": "0",
                        },
                    ),
                    httpx.Response(
                        200, json={"status": "done", "result": {"explanation": "done"}}
                    ),
                ],
            ) as send,
        ):
            async with application_clients() as (client, analysis_client):
                with patch.object(client, "head") as head:
                    head.return_value.__aenter__.return_value.status = 200
                    assert await _call_analyze_api(
                        [{"name": "build.log", "url": log_url}],
                        http_client=client,
                        analysis_client=analysis_client,
                    ) == {"explanation": "done", "extracted_snippets": []}
                with pytest.raises(aiohttp.ClientError, match="forbidden"):
                    async with client.get(f"{server_url}/log"):
                        pytest.fail("Unexpected successful request")

        requests = [call.args[0] for call in send.await_args_list]
        assert [(request.method, request.url.path) for request in requests] == [
            ("POST", "/analyze"),
            ("GET", "/tasks/1"),
        ]
        for request in requests:
            assert request.url.host == server.host
            assert request.url.port == server.port
            assert (
                request.headers["host"] == httpx.Request("GET", server).headers["host"]
            )
            assert "sni_hostname" not in request.extensions

    @pytest.mark.parametrize("scheme", ["http", "https"])
    async def test_service_environment_proxy(self, monkeypatch, scheme):
        """HTTP uses proxy forwarding; HTTPS starts a tunnel through the proxy."""
        requests = []

        async def proxy(reader, writer):
            requests.append(await reader.readline())
            await reader.readuntil(b"\r\n\r\n")
            writer.write(
                b"HTTP/1.1 407 Proxy Authentication Required\r\nContent-Length: 0\r\n\r\n"
            )
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        async with await asyncio.start_server(proxy, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            origin = f"{scheme}://analysis.invalid"
            monkeypatch.setattr("src.client.SERVER_URL", origin)
            for key in (
                "http_proxy",
                "https_proxy",
                "no_proxy",
                "NO_PROXY",
                "REQUEST_METHOD",
            ):
                monkeypatch.delenv(key, raising=False)
            monkeypatch.setenv(f"{scheme.upper()}_PROXY", f"http://127.0.0.1:{port}")
            async with application_clients() as (_, client):
                if scheme == "http":
                    assert (await client.get(origin)).status_code == 407
                    assert requests == [b"GET http://analysis.invalid/ HTTP/1.1\r\n"]
                else:
                    with pytest.raises(httpx.ProxyError):
                        await client.get(origin)
                    assert requests == [b"CONNECT analysis.invalid:443 HTTP/1.1\r\n"]

    async def test_service_no_proxy(self, monkeypatch, caplog):
        """A NO_PROXY match goes directly to the service, not the configured proxy."""

        async def serve(reader, writer):
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"HTTP/1.1 204 No Content\r\n\r\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        async with await asyncio.start_server(serve, "127.0.0.1", 0) as server:
            origin = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
            monkeypatch.setattr("src.client.SERVER_URL", origin)
            for key in ("http_proxy", "no_proxy", "REQUEST_METHOD"):
                monkeypatch.delenv(key, raising=False)
            monkeypatch.setenv("HTTP_PROXY", "http://invalid.invalid:80")
            monkeypatch.setenv("NO_PROXY", "127.0.0.1")
            async with application_clients() as (_, client):
                with caplog.at_level("INFO", logger="httpx"):
                    assert (await client.get(origin)).status_code == 204
            requests = [
                record
                for record in caplog.records
                if record.name == "httpx"
                and record.getMessage().startswith("HTTP Request:")
            ]
            assert len(requests) == 1

    @pytest.mark.parametrize(
        "redirect_target",
        [
            "https://other.internal/tasks/1",
            "https://analysis.internal:8443/tasks/1",
            "http://analysis.internal/tasks/1",
        ],
    )
    async def test_private_server_exception_does_not_follow_origin_changes(
        self, monkeypatch, redirect_target
    ):
        """A service redirect cannot extend the exception to another origin."""
        server_url = "https://analysis.internal"
        monkeypatch.setattr("src.client.SERVER_URL", server_url)
        with (
            patch.object(
                asyncio.get_running_loop(),
                "getaddrinfo",
                return_value=[dns_answer("10.0.0.1")],
            ),
            patch.object(
                httpx.AsyncHTTPTransport,
                "handle_async_request",
                return_value=httpx.Response(302, headers={"Location": redirect_target}),
            ) as send,
        ):
            async with application_clients() as (_, analysis_client):
                with pytest.raises(httpx.ConnectError, match="forbidden"):
                    await analysis_client.get(f"{server_url}/tasks/1")
            send.assert_awaited_once()

    @pytest.mark.parametrize("first_stalls", [False, True])
    @pytest.mark.parametrize("verify", [False, True])
    async def test_tls_identity_and_fallback(self, monkeypatch, first_stalls, verify):
        """Intercept TLS setup, retaining real address selection and HTTP framing."""
        requests = []
        attempted = []
        loop = asyncio.get_running_loop()
        sock_connect = loop.sock_connect

        async def serve(reader, writer):
            data = await reader.readline()
            if data:
                data += await reader.readuntil(b"\r\n\r\n")
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nlog")
                await writer.drain()
            if data:
                requests.append(data)
            writer.close()
            await writer.wait_closed()

        async def connect(sock, address):
            attempted.append(address[0])
            if address[0] == "8.8.8.8":
                if first_stalls and len(attempted) == 1:
                    await asyncio.Event().wait()
                raise ConnectionRefusedError(111, "connection refused")
            assert address[0] == "1.1.1.1"
            return await sock_connect(sock, server.sockets[0].getsockname())

        async def tls(
            protocol_factory,
            *,
            sock,
            ssl,
            server_hostname,
            create_connection=loop.create_connection,
            **_kwargs,
        ):
            assert ssl.check_hostname and ssl.verify_mode == CERT_REQUIRED
            assert server_hostname == "xn--bcher-kva.example"
            if not verify:
                sock.close()
                raise SSLCertVerificationError("certificate rejected")
            return await create_connection(protocol_factory, sock=sock)

        server = await asyncio.start_server(serve, "127.0.0.1", 0)

        async def lookup(name, *_args, **_kwargs):
            assert name == "xn--bcher-kva.example"
            return [dns_answer("8.8.8.8"), dns_answer("1.1.1.1")]

        monkeypatch.setattr(loop, "getaddrinfo", lookup)
        monkeypatch.setattr(loop, "sock_connect", connect)
        monkeypatch.setattr(loop, "create_connection", tls)
        monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9999")
        async with server, application_clients() as (remote, _):
            if verify:
                async with remote.get(
                    "https://bücher.example/log", timeout=remote_timeout(2)
                ) as response:
                    assert await response.text() == "log"
            else:
                with pytest.raises(aiohttp.ClientConnectorCertificateError):
                    async with remote.get(
                        "https://bücher.example/log", timeout=remote_timeout(2)
                    ):
                        pytest.fail("Unexpected successful request")
        assert attempted[:2] == ["8.8.8.8", "1.1.1.1"]
        if verify:
            assert len(requests) == 1
            assert b"Host: xn--bcher-kva.example\r\n" in requests[0]
        else:
            assert not requests

    async def test_redirected_download_boundary(self, monkeypatch):
        """Reject decompressed bytes above the limit and accept the exact boundary."""
        monkeypatch.setattr("src.spells.LOG_DETECTIVE_MAX_ARTIFACT_SIZE", 1)
        async with resource_server(monkeypatch) as (origin, calls, remote, _):
            with pytest.raises(MaximumArtifactSizeExceeded):
                await fetch_text(f"{origin}/large", remote)
            result = await fetch_text(f"{origin}/redirect/log", remote)
            assert result.text == "x" * 1023 + "\ufffd"
            assert calls == [
                ("GET", "/large"),
                ("GET", "/redirect/log"),
                ("GET", "/log"),
            ]

    async def test_redirected_head_reports_final_status(self, monkeypatch):
        """Report the final HEAD status rather than the redirect status."""
        async with resource_server(monkeypatch) as (origin, calls, remote, _):
            with pytest.raises(HTTPException) as exc:
                await _check_log_urls(
                    [{"name": "log", "url": f"{origin}/redirect/missing"}], remote
                )
            assert exc.value.status_code == 422
            assert "404" in exc.value.detail
            assert calls == [("HEAD", "/redirect/missing"), ("HEAD", "/missing")]

    @pytest.mark.parametrize("path", ["credentials", "private"])
    @pytest.mark.parametrize("method", ["GET", "HEAD"])
    async def test_reject_redirect_target(self, monkeypatch, method, path):
        """Stop before contacting a forbidden redirect target."""
        async with resource_server(monkeypatch) as (origin, calls, remote, _):
            with pytest.raises(aiohttp.ClientError):
                async with remote.request(method, f"{origin}/{path}"):
                    pytest.fail("Forbidden redirect returned a response")
            assert calls == [(method, f"/{path}")]

    async def test_interrupted_download(self, monkeypatch):
        """An interrupted response must free the only connection slot."""
        monkeypatch.setattr("src.ssrf.LOGDETECTIVE_MAX_CONNECTION_LIMIT", 1)
        async with resource_server(monkeypatch) as (origin, _, remote, _):
            with pytest.raises(aiohttp.ClientPayloadError):
                await fetch_text(f"{origin}/broken", remote)
            async with asyncio.timeout(2):
                assert (await fetch_text(f"{origin}/log", remote)).text.endswith(
                    "\ufffd"
                )

    @pytest.mark.parametrize("target", ["task?key=%31", "private"])
    async def test_task_location_routing(self, monkeypatch, target):
        """Poll public task locations without sharing analysis credentials or cookies."""
        monkeypatch.setattr("src.analysis.LOG_DETECTIVE_TOKEN", "service-only")
        async with resource_server(monkeypatch) as (origin, calls, remote, analysis):

            async def submit(_self, request):
                assert request.method == "POST"
                return httpx.Response(
                    202,
                    headers={
                        "Location": f"{origin}/{target}",
                        "Retry-After": "0",
                        "Set-Cookie": "service=trusted; Path=/",
                    },
                )

            monkeypatch.setattr(
                httpx.AsyncHTTPTransport, "handle_async_request", submit
            )
            operation = _call_analyze_api(
                [{"name": "log", "url": f"{origin}/log"}], remote, analysis
            )
            if target == "private":
                with pytest.raises(HTTPException) as exc:
                    await operation
                assert exc.value.status_code == 502
            else:
                assert (await operation)["explanation"] == "done"
                assert dict(analysis.cookies) == {"service": "trusted"}
            assert calls == [("HEAD", "/log"), ("GET", f"/{target}")]

    @pytest.mark.parametrize(
        ("path", "status"), [("redirect/missing", 404), ("no-location", 302)]
    )
    async def test_download_reports_final_status(self, monkeypatch, path, status):
        """Expose the final non-success status to the caller."""
        async with resource_server(monkeypatch) as (origin, _, remote, _):
            with pytest.raises(HTTPException) as exc:
                await _download_log_content(f"{origin}/{path}", remote)
            assert exc.value.status_code == status

    async def test_binary_srpm_download(self, monkeypatch):
        """Pass the downloaded RPM bytes to extraction without text decoding."""
        async with resource_server(monkeypatch) as (origin, _, remote, _):
            # Koji normally supplies a task record and relative path to the SRPM.
            koji = MagicMock()
            koji.getBuild.return_value = None
            koji.getTaskInfo.return_value = {"parent": None}
            koji.getTaskRequest.return_value = ["fixture.src.rpm"]
            monkeypatch.setattr("src.fetcher.koji.ClientSession", lambda _: koji)
            provider = KojiProvider(42, "noarch", remote)
            monkeypatch.setattr(provider, "koji_pkgs_url", origin)

            def extract(path, _directory):
                assert path.read_bytes() == b"\xed\xab\xee\xdb\x00\xff"
                return {"name": "fixture.spec", "content": "spec"}

            monkeypatch.setattr(provider, "_get_spec_file_content_from_srpm", extract)
            assert await provider.fetch_spec_file() == {
                "name": "fixture.spec",
                "content": "spec",
            }

    async def test_signed_log_targets(self, monkeypatch):
        """Signatures can cover escape spelling and repeated keys on every hop."""
        async with resource_server(monkeypatch) as (origin, calls, remote, _):
            path = "/signed/a%2Fb/sub/%31?key=%31&key=%2b"
            target = "/signed/a%2Fb/next//my%20build%32?key=%33&key=%2b"
            url = origin + path
            await _check_log_urls([{"name": "signed", "url": url}], remote)
            assert (await fetch_text(url, remote)).text.endswith("\ufffd")
            assert calls == [
                ("HEAD", path),
                ("HEAD", target),
                ("GET", path),
                ("GET", target),
            ]

    async def test_redirect_empty_query(self, monkeypatch):
        """An explicit empty query must not forward the previous URL's parameters."""
        async with resource_server(monkeypatch) as (origin, calls, remote, _):
            await fetch_text(f"{origin}/clear-query?previous=value", remote)
            assert calls == [
                ("GET", "/clear-query?previous=value"),
                ("GET", "/clear-query"),
            ]

    async def test_stacked_log_encoding(self, monkeypatch):
        """Never report a compressed payload as successful UTF-8 log text."""
        async with resource_server(monkeypatch) as (origin, _, remote, _):
            with pytest.raises(HTTPException) as exc:
                await _download_log_content(f"{origin}/stacked", remote)
            assert exc.value.status_code == 502

    async def test_redirected_post_write_timeout(self, monkeypatch):
        """A stalled upload after a 307 uses the write deadline, not the read deadline."""
        async with resource_server(monkeypatch) as (origin, _, _, analysis):

            async def redirect(_self, _request):
                return httpx.Response(307, headers={"Location": f"{origin}/upload"})

            async def stalled_write(_self, _chunk):
                await asyncio.Event().wait()

            monkeypatch.setattr(
                httpx.AsyncHTTPTransport, "handle_async_request", redirect
            )
            monkeypatch.setattr("aiohttp.http_writer.StreamWriter.write", stalled_write)
            async with asyncio.timeout(1):
                with pytest.raises(httpx.TimeoutException):
                    await analysis.post(
                        f"{SERVER_URL}/submit",
                        content=b"body",
                        timeout=httpx.Timeout(5, write=0.02),
                    )

    @pytest.mark.parametrize("port", ["bad", "65536"])
    async def test_invalid_redirect_port(self, monkeypatch, port):
        """A malformed redirect fails at preparation without consuming the only slot."""
        monkeypatch.setattr("src.ssrf.LOGDETECTIVE_MAX_CONNECTION_LIMIT", 1)
        async with resource_server(monkeypatch) as (origin, calls, remote, _):
            path = f"/bad-port/{port}"
            url = origin + path
            with pytest.raises(HTTPException) as download:
                await _download_log_content(url, remote)
            assert download.value.status_code == 502
            with pytest.raises(HTTPException) as head:
                await _check_log_urls([{"name": "log", "url": url}], remote)
            assert head.value.status_code == 422
            assert calls == [("GET", path), ("HEAD", path)]
            async with asyncio.timeout(2):
                assert (await fetch_text(f"{origin}/log", remote)).text.endswith(
                    "\ufffd"
                )

    @pytest.mark.parametrize("redirects", [9, 10])
    async def test_redirect_limit(self, monkeypatch, redirects):
        """Follow nine redirects but do not follow a tenth redirect response."""
        async with resource_server(monkeypatch) as (origin, calls, remote, _):
            url = origin + "/" + "redirect/" * redirects + "log"
            if redirects == 9:
                assert (await fetch_text(url, remote)).text.endswith("\ufffd")
                assert calls[-1] == ("GET", "/log")
            else:
                with pytest.raises(aiohttp.TooManyRedirects):
                    await fetch_text(url, remote)
                assert calls[-1] == ("GET", "/redirect/log")
            assert len(calls) == 10
