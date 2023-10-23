from enum import StrEnum


COPR_BUILD_URL = "https://copr.fedorainfracloud.org/coprs/build/{0}"
KOJI_BUILD_URL = "https://koji.fedoraproject.org/koji/buildinfo?buildID={0}"
FEEDBACK_DIR = "/var/lib/builds/feedbacks"
PACKIT_BUILD_URL = "https://dashboard.packit.dev/jobs/copr-builds"


class ProvidersEnum(StrEnum):
    packit = "packit"
    copr = "copr"
    koji = "koji"
    url = "url"
    debug = "debug"


class BuildIdTitleEnum(StrEnum):
    copr = "Copr build"
    koji = "Koji build"
    packit = "Packit build"
    url = "URL"
    debug = "Debug output"
