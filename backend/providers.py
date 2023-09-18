import requests
from functools import lru_cache
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
