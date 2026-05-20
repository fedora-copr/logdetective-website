import asyncio
import binascii
import os
import re
import subprocess
from abc import ABC, abstractmethod
from functools import cached_property, wraps
from http import HTTPStatus
from pathlib import Path
from typing import Optional

import copr.v3
import koji
import httpx
from fastapi import HTTPException

from src.constants import COPR_RESULT_TEMPLATE, LOGGER_NAME
from src.exceptions import FetchError
from src.spells import (
    get_temporary_dir,
    get_logger,
    read_text_file,
    fetch_text,
    ensure_text,
)

LOGGER = get_logger(LOGGER_NAME)


def handle_errors(func):
    """
    Decorator to catch all client API and network issues and re-raise them as
    HTTPException to API which handles them.
    """

    @wraps(func)
    async def inner(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            raise
        except (copr.v3.exceptions.CoprNoResultException, koji.GenericError) as ex:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST, detail=str(ex)
            ) from ex
        except binascii.Error as ex:
            detail = (
                "Unable to decode a log URL from the base64 hash. "
                "How did you get to this page?"
            )
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=detail) from ex
        except httpx.HTTPStatusError as ex:
            detail = f"{ex.response.status_code} {ex.response.reason_phrase}\n{ex.response.url}"
            raise HTTPException(
                status_code=ex.response.status_code, detail=detail
            ) from ex
        except subprocess.CalledProcessError as ex:
            if "No such task" in str(ex.stderr):
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    detail=ex.stderr.decode(),
                ) from ex

            if os.environ.get("ENV") != "production":
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    detail=f"stdout: {ex.stdout} stderr: {ex.stderr}",
                ) from ex

            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR) from ex

    return inner


class Provider(ABC):
    @abstractmethod
    async def fetch_logs(self) -> list[dict[str, str]]:
        """
        Fetches logs from a provider with name and content.

        Returns:
            List of dict where each dict contains log name and its content.
        """
        ...

    @abstractmethod
    async def fetch_log_urls(self) -> list[dict[str, str]]:
        """
        Returns log URLs without downloading content.

        Returns:
            List of dict where each dict contains log name and its URL.
        """
        ...


class RPMProvider(Provider):
    """
    Is able to provide spec file on top of the logs.
    """

    @abstractmethod
    async def fetch_spec_file(self) -> Optional[dict[str, str]]:
        """
        Fetches spec file with its content and name.

        Returns:
            Dict which contains spec name and its content.
        """
        ...


class CoprProvider(RPMProvider):
    copr_url = "https://copr.fedorainfracloud.org"

    def __init__(self, build_id: int, chroot: str) -> None:
        self.build_id = build_id
        self.chroot = chroot
        self.client = copr.v3.Client({"copr_url": self.copr_url})

    @handle_errors
    async def fetch_logs(self) -> list[dict[str, str]]:
        baseurl, log_names = self._get_baseurl_and_log_names()
        logs = []
        responses = await asyncio.gather(
            *[fetch_text("{}/{}".format(baseurl, name)) for name in log_names]
        )

        for name, response in zip(log_names, responses):
            response.raise_for_status()
            logs.append(
                {
                    "name": name.removesuffix(".gz"),
                    "content": response.text,
                }
            )
        return logs

    def _get_baseurl_and_log_names(self):
        log_names = ["builder-live.log.gz", "backend.log.gz"]
        if self.chroot == "srpm-builds":
            build = self.client.build_proxy.get(self.build_id)
            baseurl = COPR_RESULT_TEMPLATE.format(
                build.ownername, build.project_dirname, build.id
            )
        else:
            build_chroot = self.client.build_chroot_proxy.get(
                self.build_id, self.chroot
            )
            baseurl = build_chroot.result_url
            log_names.append("build.log.gz")

        if not baseurl:
            raise FetchError(
                "There are no results for {}/{}".format(self.build_id, self.chroot)
            )
        return baseurl, log_names

    @handle_errors
    async def fetch_log_urls(self) -> list[dict[str, str]]:
        baseurl, log_names = self._get_baseurl_and_log_names()
        return [
            {"name": name.removesuffix(".gz"), "url": "{}/{}".format(baseurl, name)}
            for name in log_names
        ]

    @handle_errors
    async def fetch_spec_file(self) -> Optional[dict[str, str]]:
        build = self.client.build_proxy.get(self.build_id)
        name = build.source_package["name"]
        if self.chroot == "srpm-builds":
            baseurl = COPR_RESULT_TEMPLATE.format(
                build.ownername, build.project_dirname, build.id
            )
        else:
            build_chroot = self.client.build_chroot_proxy.get(
                self.build_id, self.chroot
            )
            baseurl = build_chroot.result_url

        spec_name = f"{name}.spec"
        response = await fetch_text(f"{baseurl}/{spec_name}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return {"name": spec_name, "content": response.text}


class KojiProvider(RPMProvider):
    koji_url = "https://koji.fedoraproject.org"
    # checkout.log - for dist-git repo cloning problems
    logs_to_look_for = [
        "build.log",
        "root.log",
        "mock_output.log",
        "checkout.log",
        "flatpak.log",
    ]
    koji_pkgs_url = "https://kojipkgs.fedoraproject.org/work"

    task_id: int

    def __init__(self, build_or_task_id: int, arch: str) -> None:
        api_url = "{}/kojihub".format(self.koji_url)
        self.client = koji.ClientSession(api_url)

        self.arch = arch
        self.build_id = None
        # this block detects what we got: is it build or task?
        # failed builds are useless sadly, we will only work with tasks
        try:
            self.build = self.client.getBuild(build_or_task_id)
        except koji.GenericError:
            # great, no need to take care of builds
            self.build = None

        if self.build:
            self.build_id = build_or_task_id
            # it's a build, we need to find the right task now
            root_task_id = self.build["task_id"]
            # the response of getTaskDescendents:
            #   {'112162296': [{'arch': 'noarch', 'awaited': False...
            task_descendants = self.client.getTaskDescendents(root_task_id)[
                str(root_task_id)
            ]
            for task_info in task_descendants:
                if (
                    task_info["arch"] == arch
                    and task_info["method"] in ("buildArch", "buildSRPMFromSCM")
                    and task_info["state"] == 5
                ):
                    # this is the one and only ring!
                    self.task_id = task_info["id"]
                    break
            else:
                raise HTTPException(
                    detail=f"Build {build_or_task_id} doesn't have a failed task for arch {arch}",
                    status_code=HTTPStatus.BAD_REQUEST,
                )
        else:
            self.task_id = build_or_task_id

    @cached_property
    def task_info(self) -> dict:
        task = self.client.getTaskInfo(self.task_id)
        if not task:
            raise HTTPException(
                detail=f"Task {self.task_id} is empty",
                status_code=HTTPStatus.BAD_REQUEST,
            )
        return task

    @cached_property
    def task_request(self) -> list:
        return self.client.getTaskRequest(self.task_id)

    def get_task_request_url(self) -> Optional[str]:
        """
        We need this:
            'git+https://src.fedoraproject.org/rpms/libphonenumber.git#c88bd3...
        This info is in self.task_request[0]
        methods build and buildFromSCM has this
        buildArch contains file-based path to SRPM

        For scratch builds submitted from CLI:
            'cli-build/1705395313.3717997.mjCDejui/sqlite-3.45.0-1.fc40.src.rpm'
        """
        task_request_url = self.task_request[0]
        if task_request_url.startswith("git+https"):
            return task_request_url
        parent_task = self.task_info["parent"]
        if parent_task:
            task_request_url = self.client.getTaskInfo(parent_task, request=True)[
                "request"
            ][0]
        if task_request_url.startswith("git+https"):
            return task_request_url
        return None

    def _validate_task_method(self) -> None:
        if self.task_info["method"] not in (
            "buildArch",
            "buildSRPMFromSCM",
            "flatpakBuildArch",
        ):
            raise HTTPException(
                detail=(
                    f"Task {self.task_id} method is "
                    f"{self.task_info['method']}. "
                    "Please select task with method buildArch."
                ),
                status_code=HTTPStatus.BAD_REQUEST,
            )

    async def _fetch_task_logs_from_task_id(self) -> list[dict[str, str]]:
        # since we require arch in the input, we can check if the task matches it
        # but I think it's not a good UX, if the user gives us task ID, let's just use it
        # if someone complains about, just reintroduce the if below
        # if self.task_info["arch"] != self.arch:

        self._validate_task_method()

        logs = []
        # Logs are gathered sequentially for to preserve error handling
        for log_name in self.logs_to_look_for:
            try:
                log_content = await asyncio.to_thread(
                    self.client.downloadTaskOutput, self.task_id, log_name
                )
            except koji.GenericError:
                # checkout.log not available for buildArch
                continue
            # Koji API may return bytes
            logs.append({"name": log_name, "content": ensure_text(log_content)})

        return logs

    @handle_errors
    async def fetch_logs(self) -> list[dict[str, str]]:
        logs = await self._fetch_task_logs_from_task_id()

        if not logs:
            raise FetchError(
                f"No logs for build {self.build_id} task #{self.task_id} and architecture"
                f" {self.arch}"
            )

        return logs

    @handle_errors
    async def fetch_log_urls(self) -> list[dict[str, str]]:
        self._validate_task_method()
        available_logs = await asyncio.to_thread(
            self.client.listTaskOutput, self.task_id
        )
        task_relpath = f"tasks/{self.task_id % 10000}/{self.task_id}"
        urls = []
        for log_name in self.logs_to_look_for:
            if log_name in available_logs:
                urls.append(
                    {
                        "name": log_name,
                        "url": f"{self.koji_pkgs_url}/{task_relpath}/{log_name}",
                    }
                )

        if not urls:
            raise FetchError(
                f"No logs for build {self.build_id} task #{self.task_id} and architecture"
                f" {self.arch}"
            )
        return urls

    def _get_srpm_url_from_task(self) -> Optional[str]:
        # example: 'cli-build/1705395313.3717997.mjCDejui/sqlite-3.45.0-1.fc40.src.rpm'
        request_endpoint = self.task_request[0]
        if not request_endpoint.endswith(".src.rpm"):
            LOGGER.error(f"Cannot find SRPM for task {self.task_id}.")
            return None
        return f"{self.koji_pkgs_url}/{request_endpoint}"

    @staticmethod
    def _get_spec_file_content_from_srpm(
        srpm_path: Path, temp_dir: Path
    ) -> Optional[dict[str, str]]:
        # extract spec file from srpm
        cmd = f"rpm2archive -n < {str(srpm_path)} | tar xf - '*.spec'"
        subprocess.run(cmd, shell=True, check=True, cwd=temp_dir, capture_output=True)
        fst_spec_file = next(temp_dir.glob("*.spec"), None)
        if fst_spec_file is None:
            return None

        return {"name": fst_spec_file.name, "content": read_text_file(fst_spec_file)}

    async def _fetch_spec_file_from_task_id(self) -> Optional[dict[str, str]]:
        with get_temporary_dir() as temp_dir:
            srpm_url = self._get_srpm_url_from_task()
            if not srpm_url:
                return None
            async with httpx.AsyncClient() as client:
                resp = await client.get(srpm_url)
                if not resp.is_success:
                    LOGGER.error(
                        "SRPM %s for task %s not accessible: %s (%s)",
                        srpm_url,
                        self.task_id,
                        resp.status_code,
                        resp.reason_phrase,
                    )
                    return None

            destination = Path(f"{temp_dir}/{srpm_url.split('/')[-1]}")
            with open(destination, "wb") as srpm_f:
                srpm_f.write(resp.content)

            return self._get_spec_file_content_from_srpm(destination, temp_dir)

    @handle_errors
    async def fetch_spec_file(self) -> Optional[dict[str, str]]:
        """
        Fetch spec file from dist-git if possible.

        Otherwise, download the SRPM and extract spec out of it.
        """
        request_url = self.get_task_request_url()
        # request_url is not a link but rather a relative path to the SRPM
        if request_url is None:
            return await self._fetch_spec_file_from_task_id()
        package_name_matches = re.findall(r"/rpms/(.+)\.git", request_url)
        commit_hash_matches = re.findall(r"\.git#(.+)$", request_url)
        if not (package_name_matches and commit_hash_matches):
            LOGGER.error(
                "Either package name or commit hash missing from the URL: %s",
                request_url,
            )
            return None
        package_name = package_name_matches[0]
        commit_hash = commit_hash_matches[0]
        spec_url = (
            "https://src.fedoraproject.org/rpms/"
            f"{package_name}/raw/{commit_hash}/f/{package_name}.spec"
        )
        response = await fetch_text(spec_url)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            LOGGER.error(
                "No spec file found in koji for task #%s and arch %s.Reason: %s",
                self.task_id,
                self.arch,
                exc,
            )
            return None
        return {"name": f"{package_name}.spec", "content": response.text}


class PackitProvider(RPMProvider):
    """
    The `packit_id` is hard to get. Open https://prod.packit.dev/api

    1) Use the `/copr-builds` route. The results contain a dictionary
       named `packit_id_per_chroot`. Use these IDs.

    2) Use the `/koji-builds` route. The results contain `packit_id`. Use these.

    I don't know if it is possible to get the `packit_id` in a WebUI
    """

    packit_api_url = "https://prod.packit.dev/api"
    _provider: Optional[CoprProvider | KojiProvider] = None

    def __init__(self, packit_id: int) -> None:
        self.packit_id = packit_id
        self.copr_url = f"{self.packit_api_url}/copr-builds/{self.packit_id}"
        self.koji_url = f"{self.packit_api_url}/koji-builds/{self.packit_id}"

    async def _get_provider(self) -> CoprProvider | KojiProvider:
        if self._provider:
            return self._provider
        self._provider = await self._resolve_provider()
        return self._provider

    async def _resolve_provider(self) -> CoprProvider | KojiProvider:
        async with httpx.AsyncClient() as client:
            resp = await client.get(self.copr_url)
            if resp.is_success:
                build = resp.json()
                return CoprProvider(build["build_id"], build["chroot"])

            resp = await client.get(self.koji_url)
            if not resp.is_success:
                raise FetchError(
                    f"Couldn't find any build logs for Packit ID #{self.packit_id}."
                )

        build = resp.json()
        task_id = build["task_id"]
        koji_api_url = f"{KojiProvider.koji_url}/kojihub"
        koji_client = koji.ClientSession(koji_api_url)
        arch = koji_client.getTaskInfo(task_id, strict=True).get("arch")
        if arch is None:
            raise FetchError(f"No arch was found for koji task #{task_id}")

        return KojiProvider(task_id, arch)

    @handle_errors
    async def fetch_logs(self) -> list[dict[str, str]]:
        provider = await self._get_provider()
        return await provider.fetch_logs()

    @handle_errors
    async def fetch_log_urls(self) -> list[dict[str, str]]:
        provider = await self._get_provider()
        return await provider.fetch_log_urls()

    @handle_errors
    async def fetch_spec_file(self) -> Optional[dict[str, str]]:
        provider = await self._get_provider()
        return await provider.fetch_spec_file()

    async def get_url(self):
        provider = await self._get_provider()
        if isinstance(provider, CoprProvider):
            _url = "https://dashboard.packit.dev/results/copr-builds/{0}"
        else:
            _url = "https://dashboard.packit.dev/results/koji-builds/{0}"
        return _url.format(self.packit_id)


class URLProvider(RPMProvider):
    def __init__(self, url: str) -> None:
        self.url = url

    @handle_errors
    async def fetch_logs(self) -> list[dict[str, str]]:
        # TODO Can we recognize a directory listing and show _all_ logs?
        #  also this will allow us to fetch spec files
        response = await fetch_text(self.url)
        response.raise_for_status()
        if "text/plain" not in response.headers["Content-Type"]:
            raise FetchError(
                f"The URL must point to a raw text file. This URL isn't: {self.url}"
            )
        return [
            {
                "name": "Log file",
                "content": response.text,
            }
        ]

    @handle_errors
    async def fetch_log_urls(self) -> list[dict[str, str]]:
        return [{"name": "Log file", "url": self.url}]

    @handle_errors
    async def fetch_spec_file(self) -> Optional[dict[str, str]]:
        # FIXME: Please implement me!
        #  raise NotImplementedError("Please implement me!")
        return None  # type: ignore


class ContainerProvider(Provider):
    """
    Fetching container logs only from URL for now
    """

    def __init__(self, url: str) -> None:
        self.url = url

    @handle_errors
    async def fetch_logs(self) -> list[dict[str, str]]:
        # TODO: c&p from url provider for now, integrate with containers better later on
        response = await fetch_text(self.url)
        response.raise_for_status()
        if "text/plain" not in response.headers["Content-Type"]:
            raise FetchError(
                f"The URL must point to a raw text file. This URL isn't: {self.url}"
            )
        return [
            {
                "name": "Container log",
                "content": response.text,
            }
        ]

    @handle_errors
    async def fetch_log_urls(self) -> list[dict[str, str]]:
        return [{"name": "Container log", "url": self.url}]


class OBSProvider(RPMProvider):
    """
    Fetches a build log from the OBS public endpoint.
    """

    obs_log_url = (
        "https://build.opensuse.org/public/build/"
        "{project}/{repository}/{architecture}/{package}/_log"
    )
    obs_spec_url = (
        "https://build.opensuse.org/public/source/{project}/{package}/{filename}"
    )

    def __init__(
        self, project: str, repository: str, architecture: str, package: str
    ) -> None:
        self.project = project
        self.repository = repository
        self.architecture = architecture
        self.package = package

    @cached_property
    def log_url(self) -> str:
        """Return the OBS public build-log URL for this provider's coordinates."""
        return self.obs_log_url.format(
            project=self.project,
            repository=self.repository,
            architecture=self.architecture,
            package=self.package,
        )

    @handle_errors
    async def fetch_logs(self) -> list[dict[str, str]]:
        response = await fetch_text(self.log_url)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        if "text/plain" not in content_type:
            raise FetchError(
                f"The OBS log URL did not return a plain text file. URL: {self.log_url}"
            )
        return [{"name": "build.log", "content": response.text}]

    @handle_errors
    async def fetch_log_urls(self) -> list[dict[str, str]]:
        return [{"name": "build.log", "url": self.log_url}]

    @handle_errors
    async def fetch_spec_file(self) -> Optional[dict[str, str]]:
        spec_name = f"{self.package}.spec"
        url = self.obs_spec_url.format(
            project=self.project, package=self.package, filename=spec_name
        )
        response = await fetch_text(url)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return {"name": spec_name, "content": response.text}
