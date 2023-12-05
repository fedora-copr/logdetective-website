import koji
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

import responses
from copr.v3 import BuildProxy, BuildChrootProxy

from src.constants import COPR_RESULT_TEMPLATE
from src.exceptions import FetchError
from src.fetcher import CoprProvider, KojiProvider, URLProvider, PackitProvider
from tests.spells import mock_multiple_responses, sort_by_name


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
    @responses.activate
    @patch.object(BuildProxy, "get")
    @patch.object(BuildChrootProxy, "get")
    def test_fetch_copr_logs(
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
        if baseurl:
            mock_multiple_responses(baseurl, logs)

        provider = CoprProvider(123, chroot)
        if not baseurl:
            with pytest.raises(FetchError):
                provider.fetch_logs()
            return

        expected_result = sorted(
            [
                {"name": name.removesuffix(".gz"), "content": content}
                for name, content in logs.items()
            ],
            key=sort_by_name,
        )
        assert expected_result == sorted(provider.fetch_logs(), key=sort_by_name)

    @pytest.mark.parametrize(
        "chroot, baseurl",
        [
            pytest.param("fedora-39_x86_64", "https://www.XYZ.uwu"),
            pytest.param(
                "srpm-builds", COPR_RESULT_TEMPLATE.format("ownername", "dirname", 123)
            ),
        ],
    )
    @responses.activate
    @patch.object(BuildProxy, "get")
    @patch.object(BuildChrootProxy, "get")
    def test_fetch_copr_spec(
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
        responses.add(
            responses.GET, url=f"{baseurl}/{spec_name}", body=fake_spec_file, status=200
        )

        assert {"name": spec_name, "content": fake_spec_file} == CoprProvider(
            123, chroot
        ).fetch_spec_file()

        responses.add(
            responses.GET,
            url=f"{baseurl}/{spec_name}",
            json={"error": "some error msg"},
            status=404,
        )

        assert CoprProvider(123, chroot).fetch_spec_file() is None


class TestURLProvider:
    @responses.activate
    def test_fetch_url_logs(self):
        url = "https://www.fake.lol"
        provider = URLProvider(url)
        responses.add(responses.GET, url=url, body="text")
        assert provider.fetch_logs() == [{"name": "Log file", "content": "text"}]

    def test_fetch_url_spec(self):
        assert URLProvider("https://www.fake.lol").fetch_spec_file() is None


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
    def test_get_logs(self, mock_task_info, mock_client_session, f_task_dict, request):
        mock_client_session.return_value = MagicMock(
            getBuild=MagicMock(side_effect=koji.GenericError),
            downloadTaskOutput=MagicMock(return_value="LOG_CONTENT"),
        )
        mock_task_info.return_value = request.getfixturevalue(f_task_dict)
        koji_provider = KojiProvider(123, "noarch")
        logs = koji_provider.fetch_logs()
        assert len(logs) == 4
        for log in logs:
            assert log["content"] == "LOG_CONTENT"

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
    @responses.activate
    def test_fetch_spec_file_from_url(
        self, mock_client_session, mock_get_task_request_url, fake_spec_file
    ):
        mock_client_session.return_value = MagicMock(
            getBuild=MagicMock(side_effect=koji.GenericError),
        )
        mock_get_task_request_url.return_value = (
            "git+https://src.fedoraproject.org/rpms/copr-frontend.git#dbcd207"
        )
        spec_url = (
            "https://src.fedoraproject.org/rpms/copr-frontend/raw/dbcd207/f/copr-frontend.spec"
        )
        responses.add(responses.GET, url=spec_url, body=fake_spec_file, status=200)
        expected = {"name": "copr-frontend.spec", "content": fake_spec_file}
        assert expected == KojiProvider(123, "noarch").fetch_spec_file()

    @patch.object(KojiProvider, "_fetch_spec_file_from_task_id")
    @patch.object(KojiProvider, "get_task_request_url")
    @patch.object(koji, "ClientSession")
    def test_fetch_spec_file_from_task_id(
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
        assert expected == KojiProvider(123, "noarch").fetch_spec_file()

    @patch.object(KojiProvider, "_fetch_spec_file_from_task_id")
    @patch.object(KojiProvider, "get_task_request_url")
    @patch.object(koji, "ClientSession")
    def test_fetch_spec_file_from_task_id_none(
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
        assert KojiProvider(123, "noarch").fetch_spec_file() is None

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


class TestPackitProvider:
    packit_id = 123
    packit_provider = PackitProvider(packit_id)

    @responses.activate
    def test_get_correct_provider_with_copr(self):
        build_id = 456
        chroot = "fedora-39-x86_64"

        responses.add(
            responses.GET,
            url=self.packit_provider.copr_url,
            status=200,
            json={"build_id": build_id, "chroot": chroot},
        )

        correct_provider = self.packit_provider._get_correct_provider()

        assert isinstance(correct_provider, CoprProvider)
        assert correct_provider.build_id == build_id
        assert correct_provider.chroot == chroot

    @responses.activate
    @patch.object(koji, "ClientSession")
    @patch("src.fetcher.KojiProvider", autospec=True)
    def test_get_correct_provider_with_koji(
        self, mock_koji_provider, mock_client_session
    ):
        task_id = 456
        arch = "x86_64"

        responses.add(responses.GET, url=self.packit_provider.copr_url, status=404)
        responses.add(
            responses.GET,
            url=self.packit_provider.koji_url,
            status=200,
            json={"task_id": task_id},
        )

        instance = mock_koji_provider.return_value
        instance.return_value = None

        mock_client_session = MagicMock()
        mock_client_session.getTaskInfo.return_value = {"arch": arch}

        correct_provider = self.packit_provider._get_correct_provider()

        assert isinstance(correct_provider, KojiProvider)

    @responses.activate
    def test_get_correct_provider_with_no_provider(self):
        responses.add(responses.GET, url=self.packit_provider.koji_url, status=404)
        responses.add(responses.GET, url=self.packit_provider.copr_url, status=404)

        with pytest.raises(FetchError):
            self.packit_provider._get_correct_provider()
