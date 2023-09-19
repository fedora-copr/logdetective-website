import requests
from functools import lru_cache
import koji
import copr.v3
from .data import LOG_OUTPUT


def fetch_debug_logs():
    return [{
        "name": "fake-builder-live.log",
        "content": LOG_OUTPUT,
    }]


def fetch_copr_logs(build_id, chroot):
    copr_url = "https://copr.fedorainfracloud.org"
    client = copr.v3.Client({"copr_url": copr_url})
    build_chroot = client.build_chroot_proxy.get(build_id, chroot)

    logs = []
    names = ["builder-live.log.gz", "backend.log.gz", "build.log.gz"]
    for name in names:
        url = "{0}/{1}".format(build_chroot.result_url, name)
        response = requests.get(url)
        logs.append({
            "name": name.removesuffix(".gz"),
            "content": response.text,
        })
    return logs


def fetch_koji_logs(build_id, arch):
    koji_url = "https://koji.fedoraproject.org"
    api_url = "{0}/kojihub".format(koji_url)
    session = koji.ClientSession(api_url)
    logs = []
    names = ["build.log", "root.log", "mock_output.log"]
    try:
        koji_logs = session.getBuildLogs(build_id)
        for log in koji_logs:
            if log["dir"] != arch:
                continue

            if log["name"] not in names:
                continue

            url = "{0}/{1}".format(koji_url, log["path"])
            response = requests.get(url)
            logs.append({
                "name": log["name"],
                "content": response.text,
            })
        return logs
    except koji.GenericError as ex:
        # TODO Raise our exception
        print(ex)


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

    # TODO Raise our exception that Koji builds from packit are not recognized yet
    return []


def fetch_url_logs(url):
    # TODO Can we recognize a directory listing and show _all_ logs?
    response = requests.get(url)
    if response.headers["Content-Type"] != "text/plain":
        # TODO Raise
        return []

    return [{
        "name": "Log file",
        "content": response.text,
    }]
