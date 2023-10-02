import binascii
import requests
from functools import lru_cache
from base64 import b64decode
import koji
import copr.v3
from .data import LOG_OUTPUT


class FetchError(RuntimeError):
    """
    Unable to fetch the logs from the outside world for any reason.
    """


def handle_errors(func):
    """
    Decorator to catch all client API and network issues and re-raise them as
    our custom `FetchError`
    """
    def inner(*args, **kwargs):
        try:
            return func(*args, **kwargs)

        except copr.v3.exceptions.CoprNoResultException as ex:
            raise FetchError(str(ex)) from ex

        except koji.GenericError as ex:
            raise FetchError(str(ex)) from ex

        except binascii.Error as ex:
            msg = ("Unable to decode a log URL from the base64 hash. "
                   "How did you get to this page?")
            raise FetchError(msg) from ex

        except requests.HTTPError as ex:
            msg = "{0} {1}\n{2}".format(
                ex.response.status_code,
                ex.response.reason,
                ex.response.url,
            )
            raise FetchError(msg) from ex
    return inner


def fetch_debug_logs():
    return [{
        "name": "fake-builder-live.log",
        "content": LOG_OUTPUT,
    }]


@handle_errors
def fetch_copr_logs(build_id, chroot):
    copr_url = "https://copr.fedorainfracloud.org"
    client = copr.v3.Client({"copr_url": copr_url})
    build_chroot = client.build_chroot_proxy.get(build_id, chroot)

    logs = []
    names = ["builder-live.log.gz", "backend.log.gz", "build.log.gz"]
    for name in names:
        url = "{0}/{1}".format(build_chroot.result_url, name)
        response = requests.get(url)
        response.raise_for_status()
        logs.append({
            "name": name.removesuffix(".gz"),
            "content": response.text,
        })
    return logs


@handle_errors
def fetch_koji_logs(build_id, arch):
    koji_url = "https://koji.fedoraproject.org"
    api_url = "{0}/kojihub".format(koji_url)
    session = koji.ClientSession(api_url)
    logs = []
    names = ["build.log", "root.log", "mock_output.log"]

    koji_logs = session.getBuildLogs(build_id)
    for log in koji_logs:
        if log["dir"] != arch:
            continue

        if log["name"] not in names:
            continue

        url = "{0}/{1}".format(koji_url, log["path"])
        response = requests.get(url)
        response.raise_for_status()
        logs.append({
            "name": log["name"],
            "content": response.text,
        })

    if not logs:
        raise FetchError("No logs for build #{0} and architecture {1}"
                         .format(build_id, arch))
    return logs


@handle_errors
def fetch_packit_logs(packit_id):
    """
    The `packit_id` is hard to get. Open https://prod.packit.dev/api

    1) Use the `/copr-builds` route. The results contain a dictionary
       named `packit_id_per_chroot`. Use these IDs.

    2) Use the `/koji-builds` route. The results contain `packit_id`. Use these.

    I don't know if it is possible to get the `packit_id` in a WebUI
    """
    packit_url = "https://prod.packit.dev"
    url = "{0}/api/copr-builds/{1}".format(packit_url, packit_id)
    build = requests.get(url).json()
    if "copr_owner" in build:
        return fetch_copr_logs(build["build_id"], build["chroot"])

    raise FetchError("Couldn't find any build logs for Packit ID #{0}. "
                     "Please note that Packit Koji jobs are not recognized yet"
                     .format(packit_id))


@handle_errors
def decode_base64_url(encoded_url):
    return b64decode(encoded_url).decode("utf-8")


@handle_errors
def fetch_url_logs(url):
    # TODO Can we recognize a directory listing and show _all_ logs?
    response = requests.get(url)
    response.raise_for_status()
    if response.headers["Content-Type"] != "text/plain":
        raise FetchError("The URL must point to a raw text file. "
                         "This URL isn't: {0}".format(url))
    return [{
        "name": "Log file",
        "content": response.text,
    }]
