import binascii
import os
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from contextlib import contextmanager
from http import HTTPStatus
from pathlib import Path
from typing import Iterator

import copr.v3
import koji
import requests
from fastapi import HTTPException

from backend.data import LOG_OUTPUT
from backend.exceptions import FetchError


def handle_errors(func):
    """
    Decorator to catch all client API and network issues and re-raise them as
    HTTPException to API which handles them
    """

    def inner(*args, **kwargs):
        try:
            return func(*args, **kwargs)

        except copr.v3.exceptions.CoprNoResultException or koji.GenericError as ex:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST, detail=str(ex)
            ) from ex

        except binascii.Error as ex:
            detail = (
                "Unable to decode a log URL from the base64 hash. "
                "How did you get to this page?"
            )
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=detail) from ex

        except requests.HTTPError as ex:
            detail = (
                f"{ex.response.status_code} {ex.response.reason}\n{ex.response.url}"
            )
            raise HTTPException(
                status_code=ex.response.status_code, detail=detail
            ) from ex

    return inner


class Provider(ABC):
    @abstractmethod
    def fetch_logs(self) -> list[dict[str, str]]:
        ...

    @abstractmethod
    def fetch_spec_file(self) -> list[str]:
        ...


class CoprProvider(Provider):
    copr_url = "https://copr.fedorainfracloud.org"

    def __init__(self, build_id: int, chroot: str) -> None:
        self.build_id = build_id
        self.chroot = chroot
        self.client = copr.v3.Client({"copr_url": self.copr_url})

    @handle_errors
    def fetch_logs(self) -> list[dict[str, str]]:
        log_names = ["builder-live.log.gz", "backend.log.gz"]

        if self.chroot == "srpm-builds":
            build = self.client.build_proxy.get(self.build_id)
            baseurl = os.path.dirname(build.source_package["url"])
        else:
            build_chroot = self.client.build_chroot_proxy.get(
                self.build_id, self.chroot
            )
            baseurl = build_chroot.result_url
            log_names.append("build.log.gz")

        logs = []
        for name in log_names:
            url = "{}/{}".format(baseurl, name)
            response = requests.get(url)
            response.raise_for_status()
            logs.append(
                {
                    "name": name.removesuffix(".gz"),
                    "content": response.text,
                }
            )
        return logs

    @handle_errors
    def fetch_spec_file(self) -> list[str]:
        build = self.client.build_proxy.get(self.build_id)
        name = build.source_package["name"]
        if self.chroot == "srpm-builds":
            baseurl = os.path.dirname(build.source_package["url"])
        else:
            build_chroot = self.client.build_chroot_proxy.get(
                self.build_id, self.chroot
            )
            baseurl = build_chroot.result_url

        response = requests.get(f"{baseurl}/{name}.spec")
        response.raise_for_status()
        return response.text.split("\n")


class KojiProvider(Provider):
    koji_url = "https://koji.fedoraproject.org"

    def __init__(self, build_id: int, arch: str) -> None:
        self.build_id = build_id
        self.arch = arch
        api_url = "{}/kojihub".format(self.koji_url)
        self.client = koji.ClientSession(api_url)

    @handle_errors
    def fetch_logs(self) -> list[dict[str, str]]:
        logs = []
        names = ["build.log", "root.log", "mock_output.log"]

        koji_logs = self.client.getBuildLogs(self.build_id)
        for log in koji_logs:
            if log["dir"] != self.arch:
                continue

            if log["name"] not in names:
                continue

            url = "{}/{}".format(self.koji_url, log["path"])
            response = requests.get(url)
            response.raise_for_status()
            logs.append(
                {
                    "name": log["name"],
                    "content": response.text,
                }
            )

        if not logs:
            raise FetchError(
                f"No logs for build #{self.build_id} and architecture {self.arch}"
            )

        return logs

    @contextmanager
    def _create_tmp_srpm_in_temp_dir(self, srpm_url: str) -> Iterator[Path]:
        response = requests.get(srpm_url)
        temp_dir = Path(tempfile.mkdtemp())
        koji_srpm_path = temp_dir / f"koji_{self.build_id}.src.rpm"
        try:
            with open(koji_srpm_path, "wb") as src_rpm:
                src_rpm.write(response.content)

            # extract spec file from srpm
            cmd = f"rpm2archive -n < {str(koji_srpm_path)} | tar xf - '*.spec'"
            subprocess.run(cmd, shell=True, check=False, cwd=temp_dir)

            yield temp_dir
        finally:
            shutil.rmtree(temp_dir)

    @handle_errors
    def fetch_spec_file(self) -> list[str]:
        koji_logs = self.client.getBuild(self.build_id)
        srpm_url = (
            f"{self.koji_url}/packages/{koji_logs['package_name']}"
            f"/{koji_logs['version']}/{koji_logs['release']}/src/{koji_logs['nvr']}"
            ".src.rpm"
        )
        with self._create_tmp_srpm_in_temp_dir(srpm_url) as temp_dir:
            fst_spec_file = next(temp_dir.glob("*.spec"), None)
            if fst_spec_file is None:
                raise FileNotFoundError(f"No spec file found in SRPM: {srpm_url}")

            spec_content = []
            with open(fst_spec_file) as spec_file:
                spec_content.extend(spec_file.readlines())

        return spec_content


class PackitProvider(Provider):
    packit_api_url = "https://prod.packit.dev/api"

    def __init__(self, packit_id: int) -> None:
        self.packit_id = packit_id

    @handle_errors
    def fetch_logs(self) -> list[dict[str, str]]:
        # TODO: fetch also koji builds
        #  Use the `/koji-builds` route. The results contain `packit_id`. Use these.
        copr_url = f"{self.packit_api_url}/copr-builds/{self.packit_id}"
        build = requests.get(copr_url).json()
        if "copr_owner" in build:
            copr_provider = CoprProvider(build["build_id"], build["chroot"])
            return copr_provider.fetch_logs()

        raise FetchError(
            f"Couldn't find any build logs for Packit ID #{self.packit_id}. "
            "Please note that Packit Koji jobs are not recognized yet"
        )

    @handle_errors
    def fetch_spec_file(self) -> list[str]:
        # TODO: fetch also koji builds
        #  Use the `/koji-builds` route. The results contain `packit_id`. Use these.
        copr_url = f"{self.packit_api_url}/copr-builds/{self.packit_id}"
        build = requests.get(copr_url).json()
        if "copr_owner" in build:
            copr_provider = CoprProvider(build["build_id"], build["chroot"])
            return copr_provider.fetch_spec_file()

        raise FetchError(
            f"Couldn't find any build logs for Packit ID #{self.packit_id}. "
            "Please note that Packit Koji jobs are not recognized yet"
        )


class URLProvider(Provider):
    def __init__(self, url: str) -> None:
        self.url = url

    @handle_errors
    def fetch_logs(self) -> list[dict[str, str]]:
        # TODO Can we recognize a directory listing and show _all_ logs?
        #  also this will allow us to fetch spec files
        response = requests.get(self.url)
        response.raise_for_status()
        if response.headers["Content-Type"] != "text/plain":
            raise FetchError(
                "The URL must point to a raw text file. " f"This URL isn't: {self.url}"
            )
        return [
            {
                "name": "Log file",
                "content": response.text,
            }
        ]

    @handle_errors
    def fetch_spec_file(self) -> list[str]:
        raise NotImplementedError("Please implement me!")


def fetch_debug_logs():
    return [
        {
            "name": "fake-builder-live.log",
            "content": LOG_OUTPUT,
        }
    ]
