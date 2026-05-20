import koji
import pytest
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock

import httpx
from copr.v3 import BuildProxy, BuildChrootProxy
from fastapi import HTTPException

from src.constants import COPR_RESULT_TEMPLATE
from src.exceptions import FetchError
from src.fetcher import (
    CoprProvider,
    KojiProvider,
    URLProvider,
    PackitProvider,
    ContainerProvider,
    OBSProvider,
)
from tests.spells import sort_by_name


def _mock_fetch_text(url_to_response: dict[str, tuple[str, int]]):
    """Create an AsyncMock for fetch_text that returns httpx.Response objects
    based on URL matching."""

    async def _fake_fetch_text(url, **kwargs):
        body, status_code = url_to_response[url]
        return httpx.Response(
            status_code=status_code,
            text=body,
            request=httpx.Request("GET", url),
        )

    return _fake_fetch_text


class TestCoprProvider:
    @pytest.mark.parametrize(
        "chroot, baseurl",
        [
            pytest.param("fedora-39_x86_64", "https://www.XYZ.uwu"),
            pytest.param(
                "srpm-builds", COPR_RESULT_TEMPLATE.format("ownername", "dirname", 123)
            ),
            pytest.param("fedora-39_x86_64", None),
        ],
    )
    @patch.object(BuildProxy, "get")
    @patch.object(BuildChrootProxy, "get")
    async def test_fetch_copr_logs(
        self,
        mock_build_chroot_proxy,
        mock_build_proxy,
        chroot,
        baseurl,
        copr_chroot_logs,
        copr_srpm_logs,
    ):
        mock_build_chroot_proxy.return_value = MagicMock(result_url=baseurl)
        mock_build_proxy.return_value = MagicMock(
            ownername="ownername", project_dirname="dirname", id=123
        )

        logs = copr_srpm_logs if chroot == "srpm-builds" else copr_chroot_logs

        provider = CoprProvider(123, chroot)
        if not baseurl:
            with pytest.raises(FetchError):
                await provider.fetch_logs()
            return

        url_map = {
            f"{baseurl}/{name}": (content, 200) for name, content in logs.items()
        }

        expected_result = sorted(
            [
                {"name": name.removesuffix(".gz"), "content": content}
                for name, content in logs.items()
            ],
            key=sort_by_name,
        )
        with patch("src.fetcher.fetch_text", side_effect=_mock_fetch_text(url_map)):
            result = await provider.fetch_logs()
        assert expected_result == sorted(result, key=sort_by_name)

    @pytest.mark.parametrize(
        "chroot, baseurl",
        [
            pytest.param("fedora-39_x86_64", "https://www.XYZ.uwu"),
            pytest.param(
                "srpm-builds", COPR_RESULT_TEMPLATE.format("ownername", "dirname", 123)
            ),
        ],
    )
    @patch.object(BuildProxy, "get")
    @patch.object(BuildChrootProxy, "get")
    async def test_fetch_copr_spec(
        self, mock_build_chroot_proxy, mock_build_proxy, chroot, baseurl, fake_spec_file
    ):
        mock_build_chroot_proxy.return_value = MagicMock(result_url=baseurl)
        projectname = "pikachu"
        mock_build_proxy.return_value = MagicMock(
            source_package={"name": projectname, "url": baseurl},
            id=123,
            ownername="ownername",
            project_dirname="dirname",
        )

        spec_name = f"{projectname}.spec"
        url_map = {f"{baseurl}/{spec_name}": (fake_spec_file, 200)}

        with patch("src.fetcher.fetch_text", side_effect=_mock_fetch_text(url_map)):
            result = await CoprProvider(123, chroot).fetch_spec_file()
        assert {"name": spec_name, "content": fake_spec_file} == result

        url_map_404 = {f"{baseurl}/{spec_name}": ("", 404)}
        with patch("src.fetcher.fetch_text", side_effect=_mock_fetch_text(url_map_404)):
            result = await CoprProvider(123, chroot).fetch_spec_file()
        assert result is None

    @patch.object(BuildProxy, "get")
    @patch.object(BuildChrootProxy, "get")
    async def test_fetch_copr_logs_with_utf8(
        self, mock_build_chroot_proxy, mock_build_proxy
    ):
        baseurl = "https://copr.example.com/results"
        chroot = "fedora-39-x86_64"
        czech_log = "Chyba: závislost 'žluťoučký-balíček' nebyla nalezena"

        mock_build_chroot_proxy.return_value = MagicMock(result_url=baseurl)
        mock_build_proxy.return_value = MagicMock(
            ownername="owner", project_dirname="project", id=123
        )

        url_map = {
            f"{baseurl}/{name}": (czech_log, 200)
            for name in ["builder-live.log.gz", "backend.log.gz", "build.log.gz"]
        }

        provider = CoprProvider(123, chroot)
        with patch("src.fetcher.fetch_text", side_effect=_mock_fetch_text(url_map)):
            logs = await provider.fetch_logs()

        for log in logs:
            assert log["content"] == czech_log
            assert isinstance(log["content"], str)

    @pytest.mark.parametrize(
        "chroot, baseurl",
        [
            pytest.param("fedora-39_x86_64", "https://www.XYZ.uwu"),
            pytest.param(
                "srpm-builds", COPR_RESULT_TEMPLATE.format("ownername", "dirname", 123)
            ),
        ],
    )
    @patch.object(BuildProxy, "get")
    @patch.object(BuildChrootProxy, "get")
    async def test_fetch_log_urls(
        self,
        mock_build_chroot_proxy,
        mock_build_proxy,
        chroot,
        baseurl,
    ):
        mock_build_chroot_proxy.return_value = MagicMock(result_url=baseurl)
        mock_build_proxy.return_value = MagicMock(
            ownername="ownername", project_dirname="dirname", id=123
        )
        provider = CoprProvider(123, chroot)
        result = await provider.fetch_log_urls()

        for entry in result:
            assert "name" in entry
            assert "url" in entry
            assert entry["url"].startswith(baseurl)

        names = [e["name"] for e in result]
        assert "builder-live.log" in names
        assert "backend.log" in names
        if chroot != "srpm-builds":
            assert "build.log" in names

    @patch.object(BuildProxy, "get")
    @patch.object(BuildChrootProxy, "get")
    async def test_fetch_log_urls_no_results(
        self, mock_build_chroot_proxy, mock_build_proxy
    ):
        mock_build_chroot_proxy.return_value = MagicMock(result_url=None)
        mock_build_proxy.return_value = MagicMock(
            ownername="ownername", project_dirname="dirname", id=123
        )
        provider = CoprProvider(123, "fedora-39_x86_64")
        with pytest.raises(FetchError):
            await provider.fetch_log_urls()


class TestURLProvider:
    async def test_fetch_url_logs(self):
        url = "https://www.fake.lol"
        provider = URLProvider(url)
        url_map = {url: ("text", 200)}
        with patch("src.fetcher.fetch_text", side_effect=_mock_fetch_text(url_map)):
            result = await provider.fetch_logs()
        assert result == [{"name": "Log file", "content": "text"}]

    async def test_fetch_url_spec(self):
        assert await URLProvider("https://www.fake.lol").fetch_spec_file() is None

    async def test_fetch_url_logs_with_utf8(self):
        url = "https://www.fake.lol/log.txt"
        czech_content = "Chyba: balíček nebyl nalezen\nŘešení: přidejte repozitář"
        provider = URLProvider(url)
        url_map = {url: (czech_content, 200)}
        with patch("src.fetcher.fetch_text", side_effect=_mock_fetch_text(url_map)):
            logs = await provider.fetch_logs()
        assert logs[0]["content"] == czech_content

    async def test_fetch_log_urls(self):
        url = "https://www.fake.lol/build.log"
        provider = URLProvider(url)
        result = await provider.fetch_log_urls()
        assert result == [{"name": "Log file", "url": url}]


class TestOBSProvider:
    """Unit tests for OBSProvider log, log-URL, and spec-file fetching."""

    project = "openSUSE:Factory"
    repository = "standard"
    architecture = "x86_64"
    package = "ed"
    expected_log_url = (
        "https://build.opensuse.org/public/build/"
        "openSUSE:Factory/standard/x86_64/ed/_log"
    )
    expected_spec_url = (
        "https://build.opensuse.org/public/source/openSUSE:Factory/ed/ed.spec"
    )

    def _provider(self):
        return OBSProvider(
            self.project, self.repository, self.architecture, self.package
        )

    async def test_fetch_logs(self):
        """fetch_logs returns the OBS build log content as a single entry."""
        url_map = {self.expected_log_url: ("obs log content", 200)}
        with patch("src.fetcher.fetch_text", side_effect=_mock_fetch_text(url_map)):
            result = await self._provider().fetch_logs()
        assert result == [{"name": "build.log", "content": "obs log content"}]

    async def test_fetch_log_urls(self):
        """fetch_log_urls returns the OBS log URL without downloading content."""
        result = await self._provider().fetch_log_urls()
        assert result == [{"name": "build.log", "url": self.expected_log_url}]

    async def test_fetch_spec_file_success(self, fake_spec_file):
        """fetch_spec_file returns the spec contents when the URL responds 200."""
        url_map = {self.expected_spec_url: (fake_spec_file, 200)}
        with patch("src.fetcher.fetch_text", side_effect=_mock_fetch_text(url_map)):
            result = await self._provider().fetch_spec_file()
        assert result == {"name": "ed.spec", "content": fake_spec_file}

    async def test_fetch_spec_file_missing(self):
        """fetch_spec_file returns None when OBS responds 404."""
        url_map = {self.expected_spec_url: ("", 404)}
        with patch("src.fetcher.fetch_text", side_effect=_mock_fetch_text(url_map)):
            result = await self._provider().fetch_spec_file()
        assert result is None

    async def test_fetch_logs_http_error(self):
        """fetch_logs raises HTTPException"""
        url_map = {self.expected_log_url: ("", 404)}
        with patch("src.fetcher.fetch_text", side_effect=_mock_fetch_text(url_map)):
            with pytest.raises(HTTPException) as exc_info:
                await self._provider().fetch_logs()
            assert exc_info.value.status_code == 404


class TestKojiProviderLogs:
    @pytest.mark.parametrize(
        "f_task_dict",
        [
            pytest.param("srpm_task_dict"),
            pytest.param("rpm_build_noarch_task_dict"),
            pytest.param("rpm_build_arch_task_dict"),
        ],
    )
    @patch.object(koji, "ClientSession")
    @patch.object(KojiProvider, "task_info", new_callable=PropertyMock)
    async def test_get_logs(
        self, mock_task_info, mock_client_session, f_task_dict, request
    ):
        mock_client_session.return_value = MagicMock(
            getBuild=MagicMock(side_effect=koji.GenericError),
            downloadTaskOutput=MagicMock(return_value="LOG_CONTENT"),
        )
        mock_task_info.return_value = request.getfixturevalue(f_task_dict)
        koji_provider = KojiProvider(123, "noarch")
        logs = await koji_provider.fetch_logs()
        assert len(logs) == 5
        for log in logs:
            assert log["content"] == "LOG_CONTENT"

    @patch.object(koji, "ClientSession")
    @patch.object(KojiProvider, "task_info", new_callable=PropertyMock)
    async def test_get_logs_decodes_bytes(
        self, mock_task_info, mock_client_session, srpm_task_dict
    ):
        czech_log = "Chyba při kompilaci: žádný takový soubor"
        mock_client_session.return_value = MagicMock(
            getBuild=MagicMock(side_effect=koji.GenericError),
            downloadTaskOutput=MagicMock(return_value=czech_log.encode("utf-8")),
        )
        mock_task_info.return_value = srpm_task_dict
        koji_provider = KojiProvider(123, "noarch")
        logs = await koji_provider.fetch_logs()
        for log in logs:
            assert log["content"] == czech_log
            assert isinstance(log["content"], str)

    @pytest.mark.parametrize(
        "task_request, get_task_info, result",
        [
            pytest.param(
                ["git+https://src.fedoraproject.org/rpms/libphonenumber.git#c88bd3"],
                None,
                "git+https://src.fedoraproject.org/rpms/libphonenumber.git#c88bd3",
            ),
            pytest.param(
                ["something_else"],
                "git+https://src.fedoraproject.org/rpms/libphonenumber.git#c88bd3",
                "git+https://src.fedoraproject.org/rpms/libphonenumber.git#c88bd3",
            ),
            pytest.param(
                ["something_else"],
                "asdjkljklasdjklasdjkl",
                None,
            ),
        ],
    )
    def test_get_task_request_url(self, task_request, get_task_info, result):
        mock_self = MagicMock(
            task_request=task_request,
            task_info={"parent": get_task_info},
            client=MagicMock(
                getBuild=MagicMock(side_effect=koji.GenericError),
                getTaskInfo=MagicMock(return_value={"request": [get_task_info]}),
            ),
        )
        assert result == KojiProvider.get_task_request_url(mock_self)

    @patch.object(KojiProvider, "get_task_request_url")
    @patch.object(koji, "ClientSession")
    async def test_fetch_spec_file_from_url(
        self, mock_client_session, mock_get_task_request_url, fake_spec_file
    ):
        mock_client_session.return_value = MagicMock(
            getBuild=MagicMock(side_effect=koji.GenericError),
        )
        mock_get_task_request_url.return_value = (
            "git+https://src.fedoraproject.org/rpms/copr-frontend.git#dbcd207"
        )
        spec_url = "https://src.fedoraproject.org/rpms/copr-frontend/raw/dbcd207/f/copr-frontend.spec"  # pylint: disable=line-too-long
        url_map = {spec_url: (fake_spec_file, 200)}
        expected = {"name": "copr-frontend.spec", "content": fake_spec_file}
        with patch("src.fetcher.fetch_text", side_effect=_mock_fetch_text(url_map)):
            result = await KojiProvider(123, "noarch").fetch_spec_file()
        assert expected == result

    @patch.object(KojiProvider, "_fetch_spec_file_from_task_id", new_callable=AsyncMock)
    @patch.object(KojiProvider, "get_task_request_url")
    @patch.object(koji, "ClientSession")
    async def test_fetch_spec_file_from_task_id(
        self,
        mock_client_session,
        mock_get_task_request_url,
        mock_fetch_spec_file_from_task_id,
        fake_spec_file,
    ):
        mock_client_session.return_value = MagicMock(
            getBuild=MagicMock(side_effect=koji.GenericError),
        )
        mock_get_task_request_url.return_value = None
        expected = {"name": "copr-fronend.spec", "content": fake_spec_file}
        mock_fetch_spec_file_from_task_id.return_value = expected
        result = await KojiProvider(123, "noarch").fetch_spec_file()
        assert expected == result

    @patch.object(KojiProvider, "_fetch_spec_file_from_task_id", new_callable=AsyncMock)
    @patch.object(KojiProvider, "get_task_request_url")
    @patch.object(koji, "ClientSession")
    async def test_fetch_spec_file_from_task_id_none(
        self,
        mock_client_session,
        mock_get_task_request_url,
        mock_fetch_spec_file_from_task_id,
        fake_spec_file,
    ):
        mock_client_session.return_value = MagicMock(
            getBuild=MagicMock(side_effect=koji.GenericError),
        )
        mock_get_task_request_url.return_value = None
        mock_fetch_spec_file_from_task_id.return_value = None
        koji_result = await KojiProvider(123, "noarch").fetch_spec_file()
        assert koji_result is None

    @patch.object(koji, "ClientSession")
    def test_build_id_to_task_id(
        self, mock_client_session, copr_build_dict, copr_task_descendants
    ):
        root_task_id = copr_build_dict["task_id"]
        mock_client_session.return_value = MagicMock(
            getBuild=MagicMock(return_value=copr_build_dict),
            getTaskDescendents=MagicMock(
                return_value={str(root_task_id): copr_task_descendants}
            ),
        )
        KojiProvider(123, "noarch")

    @patch.object(koji, "ClientSession")
    @patch.object(KojiProvider, "task_info", new_callable=PropertyMock)
    async def test_fetch_log_urls(
        self, mock_task_info, mock_client_session, srpm_task_dict
    ):
        task_id = 123
        available_files = ["build.log", "root.log", "mock_output.log", "state.log"]
        mock_client_session.return_value = MagicMock(
            getBuild=MagicMock(side_effect=koji.GenericError),
            listTaskOutput=MagicMock(return_value=available_files),
        )
        mock_task_info.return_value = srpm_task_dict
        provider = KojiProvider(task_id, "noarch")
        result = await provider.fetch_log_urls()

        expected_relpath = f"tasks/{task_id % 10000}/{task_id}"
        for entry in result:
            assert "name" in entry
            assert "url" in entry
            assert expected_relpath in entry["url"]

        names = [e["name"] for e in result]
        assert "build.log" in names
        assert "root.log" in names
        assert "mock_output.log" in names
        assert "state.log" not in names

    @patch.object(koji, "ClientSession")
    @patch.object(KojiProvider, "task_info", new_callable=PropertyMock)
    async def test_fetch_log_urls_no_logs(
        self, mock_task_info, mock_client_session, srpm_task_dict
    ):
        mock_client_session.return_value = MagicMock(
            getBuild=MagicMock(side_effect=koji.GenericError),
            listTaskOutput=MagicMock(return_value=["state.log"]),
        )
        mock_task_info.return_value = srpm_task_dict
        provider = KojiProvider(123, "noarch")
        with pytest.raises(FetchError):
            await provider.fetch_log_urls()


class TestPackitProvider:
    packit_id = 123
    packit_provider = PackitProvider(packit_id)

    @patch.object(BuildProxy, "get")
    @patch.object(BuildChrootProxy, "get")
    async def test_fetch_logs_with_utf8_via_copr(
        self, mock_build_chroot_proxy, mock_build_proxy
    ):
        build_id = 456
        chroot = "fedora-39-x86_64"
        baseurl = "https://copr.example.com/results"
        czech_log = "Sestavení selhalo: chybí závislost"

        mock_build_chroot_proxy.return_value = MagicMock(result_url=baseurl)
        mock_build_proxy.return_value = MagicMock(
            ownername="owner", project_dirname="project", id=build_id
        )

        url_map = {
            f"{baseurl}/{name}": (czech_log, 200)
            for name in ["builder-live.log.gz", "backend.log.gz", "build.log.gz"]
        }

        def _transport_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"build_id": build_id, "chroot": chroot},
            )

        transport = httpx.MockTransport(_transport_handler)

        with patch(
            "src.fetcher.httpx.AsyncClient",
            return_value=httpx.AsyncClient(transport=transport),
        ):
            with patch("src.fetcher.fetch_text", side_effect=_mock_fetch_text(url_map)):
                provider = PackitProvider(self.packit_id)
                logs = await provider.fetch_logs()

        for log in logs:
            assert log["content"] == czech_log

    async def test_resolve_provider_with_copr(self):
        build_id = 456
        chroot = "fedora-39-x86_64"

        def _handler(request: httpx.Request) -> httpx.Response:
            if "copr-builds" in str(request.url):
                return httpx.Response(
                    200, json={"build_id": build_id, "chroot": chroot}
                )
            return httpx.Response(404)

        transport = httpx.MockTransport(_handler)
        provider = PackitProvider(self.packit_id)

        with patch(
            "src.fetcher.httpx.AsyncClient",
            return_value=httpx.AsyncClient(transport=transport),
        ):
            correct_provider = await provider._resolve_provider()

        assert isinstance(correct_provider, CoprProvider)
        assert correct_provider.build_id == build_id
        assert correct_provider.chroot == chroot

    @patch.object(koji, "ClientSession")
    async def test_resolve_provider_with_koji(self, mock_client_session):
        task_id = 456
        arch = "x86_64"

        mock_client_session.return_value = MagicMock(
            getBuild=MagicMock(side_effect=koji.GenericError),
            getTaskInfo=MagicMock(return_value={"arch": arch}),
        )

        def _handler(request: httpx.Request) -> httpx.Response:
            if "copr-builds" in str(request.url):
                return httpx.Response(404)
            if "koji-builds" in str(request.url):
                return httpx.Response(200, json={"task_id": task_id})
            return httpx.Response(404)

        transport = httpx.MockTransport(_handler)
        provider = PackitProvider(self.packit_id)

        with patch(
            "src.fetcher.httpx.AsyncClient",
            return_value=httpx.AsyncClient(transport=transport),
        ):
            correct_provider = await provider._resolve_provider()

        assert isinstance(correct_provider, KojiProvider)

    async def test_resolve_provider_with_no_provider(self):
        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404)

        transport = httpx.MockTransport(_handler)
        provider = PackitProvider(self.packit_id)

        with patch(
            "src.fetcher.httpx.AsyncClient",
            return_value=httpx.AsyncClient(transport=transport),
        ):
            with pytest.raises(FetchError):
                await provider._resolve_provider()

    async def test_get_url_copr(self):
        mock_copr = MagicMock(spec=CoprProvider)
        provider = PackitProvider(self.packit_id)
        with patch.object(
            provider, "_get_provider", new=AsyncMock(return_value=mock_copr)
        ):
            url = await provider.get_url()
        assert (
            url == f"https://dashboard.packit.dev/results/copr-builds/{self.packit_id}"
        )

    async def test_get_url_koji(self):
        mock_koji = MagicMock(spec=KojiProvider)
        provider = PackitProvider(self.packit_id)
        with patch.object(
            provider, "_get_provider", new=AsyncMock(return_value=mock_koji)
        ):
            url = await provider.get_url()
        assert (
            url == f"https://dashboard.packit.dev/results/koji-builds/{self.packit_id}"
        )

    async def test_fetch_log_urls(self):
        fake_urls = [{"name": "build.log", "url": "https://example.com/build.log"}]
        mock_inner = AsyncMock()
        mock_inner.fetch_log_urls = AsyncMock(return_value=fake_urls)
        provider = PackitProvider(self.packit_id)
        with patch.object(
            provider, "_get_provider", new=AsyncMock(return_value=mock_inner)
        ):
            result = await provider.fetch_log_urls()
        assert result == fake_urls


class TestContainerProvider:
    async def test_fetch_logs(self):
        url = "https://example.com/container.log"
        content = "container build output"

        async def _fake_fetch_text(u, **kwargs):
            return httpx.Response(
                200,
                text=content,
                headers={"Content-Type": "text/plain"},
                request=httpx.Request("GET", u),
            )

        provider = ContainerProvider(url)
        with patch("src.fetcher.fetch_text", side_effect=_fake_fetch_text):
            result = await provider.fetch_logs()
        assert result == [{"name": "Container log", "content": content}]

    async def test_fetch_logs_non_text_content_type(self):
        url = "https://example.com/page.html"

        async def _fake_fetch_text(u, **kwargs):
            return httpx.Response(
                200,
                text="<html></html>",
                headers={"Content-Type": "text/html"},
                request=httpx.Request("GET", u),
            )

        provider = ContainerProvider(url)
        with patch("src.fetcher.fetch_text", side_effect=_fake_fetch_text):
            with pytest.raises(FetchError):
                await provider.fetch_logs()

    async def test_fetch_logs_http_error(self):
        url = "https://example.com/missing.log"

        async def _fake_fetch_text(u, **kwargs):
            return httpx.Response(
                500,
                text="Internal Server Error",
                headers={"Content-Type": "text/plain"},
                request=httpx.Request("GET", u),
            )

        provider = ContainerProvider(url)
        with patch("src.fetcher.fetch_text", side_effect=_fake_fetch_text):
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await provider.fetch_logs()
            assert exc_info.value.status_code == 500

    async def test_fetch_log_urls(self):
        url = "https://example.com/container.log"
        provider = ContainerProvider(url)
        result = await provider.fetch_log_urls()
        assert result == [{"name": "Container log", "url": url}]
