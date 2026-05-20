import os
from enum import StrEnum
from pathlib import Path


COPR_BUILD_URL = "https://copr.fedorainfracloud.org/coprs/build/{0}"
KOJI_BUILD_URL = "https://koji.fedoraproject.org/koji/buildinfo?buildID={0}"
OBS_BUILD_URL = "https://build.opensuse.org/package/show/{0}/{1}"
FEEDBACK_DIR = os.environ.get("FEEDBACK_DIR", "/persistent/results")
REVIEWS_DIR = os.environ.get("REVIEWS_DIR", "/persistent/reviews")

LOGDETECTIVE_READ_TIMEOUT = float(os.environ.get("LOGDETECTIVE_READ_TIMEOUT", 1800))
# Set to slightly more than retransmission window of 3s from RFC2988
# https://datatracker.ietf.org/doc/html/rfc2988
LOGDETECTIVE_CONNECT_TIMEOUT = float(
    os.environ.get("LOGDETECTIVE_CONNECT_TIMEOUT", 3.07)
)
LOGDETECTIVE_DEFAULT_TIMEOUT = float(
    os.environ.get("LOGDETECTIVE_DEFAULT_TIMEOUT", 3.07)
)

COPR_RESULT_TEMPLATE = (
    "https://download.copr.fedorainfracloud.org" + "/results/{0}/{1}/srpm-builds/{2:08}"
)
# logdetective inference server URL we will query
SERVER_URL = os.environ.get("SERVER_URL", "http://127.0.0.1:8000")

# Token used for authorization of analysis requests
LOG_DETECTIVE_TOKEN = os.environ.get("LOG_DETECTIVE_TOKEN")


class ProvidersEnum(StrEnum):
    packit = "packit"
    copr = "copr"
    koji = "koji"
    url = "url"
    container = "container"
    debug = "debug"
    upload = "upload"
    obs = "obs"  # pylint: disable=invalid-name


class BuildIdTitleEnum(StrEnum):
    copr = "Copr build"
    koji = "Koji build"
    packit = "Packit build"
    url = "URL"
    container = "Container log"
    debug = "Debug output"
    obs = "OBS build"  # pylint: disable=invalid-name


PROVIDER_COMMENTARY: dict[str, str] = {
    ProvidersEnum.copr: (
        "Logs are from a Copr build.\n"
        "Copr builds use mock chroots; build.log contains mock output,\n"
        "builder-live.log contains the actual build output."
    ),
    ProvidersEnum.koji: (
        "Logs are from a Koji build.\n"
        "Koji builds use mock chroots; build.log contains build output,\n"
        "root.log has dependency resolution and mock setup."
    ),
    ProvidersEnum.packit: (
        "Logs are from a Packit CI job.\n"
        "Packit triggers builds in Copr or Koji on behalf of a pull request.\n"
        "Interpret logs as you would for the underlying build system."
    ),
    ProvidersEnum.obs: (
        "Logs are from an OBS build.\n"
        "OBS builds run in a chroot similar to mock; all build output\n"
        "is contained in build.log."
    ),
    ProvidersEnum.url: (
        "Log was submitted as a raw URL.\n"
        "No build system metadata is available.\n"
        "Treat it as a generic RPM build log."
    ),
    ProvidersEnum.container: (
        "Log is from a container build.\n"
        "Expect Dockerfile/Containerfile instructions, layer output,\n"
        "and package installation logs rather than RPM spec macros."
    ),
}

LOGGER_NAME = "logdetective_website"

STATIC_SOURCE_DIR = Path(__file__).parent.parent.parent / "frontend" / "public"

DEFAULT_ROBOTS = """
User-Agent: *
DisallowAITraining: /
Content-Usage: ai=n
Allow: /
"""
