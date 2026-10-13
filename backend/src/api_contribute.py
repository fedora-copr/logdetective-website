"""Contribution API routes."""

import uuid
from base64 import b64decode
from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel

from src.constants import (
    COPR_BUILD_URL,
    KOJI_BUILD_URL,
    LOGGER_NAME,
    OBS_BUILD_URL,
    BuildIdTitleEnum,
    ProvidersEnum,
)
from src.fetcher import (
    ContainerProvider,
    CoprProvider,
    KojiProvider,
    OBSProvider,
    PackitProvider,
    URLProvider,
)
from src.schema import ContributeResponseSchema, FeedbackInputSchema, schema_inp_to_out
from src.spells import get_logger, sanitize_uploaded_schema
from src.store import Storator3000

LOGGER = get_logger(LOGGER_NAME)
router = APIRouter()


# pylint: disable=too-many-arguments, too-many-positional-arguments
async def _get_build_logs_with_chroot(
    provider_class,
    build_id: int,
    chroot: str,
    request: Request,
    build_title,
    build_url: str,
) -> ContributeResponseSchema:
    """Fetch logs and spec data for a chroot-based build provider."""
    provider = provider_class(
        build_id, chroot, http_client=request.app.state.http_client
    )
    return ContributeResponseSchema(
        build_id=build_id,
        build_id_title=build_title,
        build_url=build_url.format(build_id),
        logs=await provider.fetch_logs(),
        spec_file=await provider.fetch_spec_file(),
    )


@router.get("/frontend/contribute/copr/{build_id}/{chroot}")
async def get_copr_build_logs(
    request: Request, build_id: int, chroot: str
) -> ContributeResponseSchema:
    """Fetch logs for a Copr build."""
    return await _get_build_logs_with_chroot(
        CoprProvider, build_id, chroot, request, BuildIdTitleEnum.copr, COPR_BUILD_URL
    )


@router.get("/frontend/contribute/koji/{build_id}/{chroot}")
async def get_koji_build_logs(
    request: Request, build_id: int, chroot: str
) -> ContributeResponseSchema:
    """Fetch logs for a Koji build."""
    return await _get_build_logs_with_chroot(
        KojiProvider, build_id, chroot, request, BuildIdTitleEnum.koji, KOJI_BUILD_URL
    )


@router.get("/frontend/contribute/packit/{packit_id}")
async def get_packit_build_logs(
    request: Request, packit_id: int
) -> ContributeResponseSchema:
    """Fetch logs for a Packit build."""
    provider = PackitProvider(packit_id, http_client=request.app.state.http_client)
    return ContributeResponseSchema(
        build_id=packit_id,
        build_id_title=BuildIdTitleEnum.packit,
        build_url=await provider.get_url(),
        logs=await provider.fetch_logs(),
        spec_file=await provider.fetch_spec_file(),
    )


@router.get("/frontend/contribute/url/{base64}")
async def get_build_logs_from_url(
    request: Request, base64: str
) -> ContributeResponseSchema:
    """Fetch logs from a URL encoded as base64."""
    build_url = b64decode(base64).decode("utf-8")
    provider = URLProvider(build_url, http_client=request.app.state.http_client)
    return ContributeResponseSchema(
        build_id=None,
        build_id_title=BuildIdTitleEnum.url,
        build_url=build_url,
        logs=await provider.fetch_logs(),
        spec_file=None,
    )


@router.get("/frontend/contribute/container/{base64}")
async def get_logs_from_container(
    request: Request, base64: str
) -> ContributeResponseSchema:
    """Fetch logs from a container URL encoded as base64."""
    build_url = b64decode(base64).decode("utf-8")
    provider = ContainerProvider(build_url, http_client=request.app.state.http_client)
    return ContributeResponseSchema(
        build_id=None,
        build_id_title=BuildIdTitleEnum.container,
        build_url=build_url,
        logs=await provider.fetch_logs(),
    )


@router.get("/frontend/contribute/obs/{project}/{repository}/{architecture}/{package}")
async def get_obs_build_logs(
    request: Request, project: str, repository: str, architecture: str, package: str
) -> ContributeResponseSchema:
    """Fetch logs for an openSUSE Build Service package."""
    provider = OBSProvider(
        project,
        repository,
        architecture,
        package,
        http_client=request.app.state.http_client,
    )
    return ContributeResponseSchema(
        build_id=None,
        build_id_title=BuildIdTitleEnum.obs,
        build_url=OBS_BUILD_URL.format(project, package),
        logs=await provider.fetch_logs(),
        spec_file=await provider.fetch_spec_file(),
    )


class OkResponse(BaseModel):
    """Response for a successful annotation submission."""

    status: str = "ok"
    review_id: str | uuid.UUID
    review_url_website: str
    review_url_json: str

    @staticmethod
    def from_id(id_: str | uuid.UUID, our_server: str) -> "OkResponse":
        """Build a response containing both public URLs for a review."""
        return OkResponse(
            review_id=id_,
            review_url_json=f"{our_server}/frontend/review/{id_}",
            review_url_website=f"{our_server}/review/{id_}",
        )


def _store_data_for_providers(
    feedback_input: FeedbackInputSchema,
    provider: str,
    id_: int | str,
    *args,
    our_server: str = "https://logdetective.com",
) -> OkResponse:
    storator = Storator3000(ProvidersEnum[provider], str(id_))
    result_to_store = schema_inp_to_out(
        feedback_input, is_with_spec=provider != ProvidersEnum.container
    )
    contribution_id = storator.store(sanitize_uploaded_schema(result_to_store))
    rest = f"/{args[0]}" if args else ""
    LOGGER.info(
        "Submitted data for %s: #%s(submission ID: %s) Additional args: %s",
        provider,
        id_,
        contribution_id,
        rest,
    )
    return OkResponse.from_id(contribution_id, our_server)


def _server_url(request: Request) -> str:
    return f"{request.url.scheme}://{request.url.netloc}"


@router.post("/frontend/contribute/copr/{build_id}/{chroot}")
def contribute_review_copr(
    feedback_input: FeedbackInputSchema, build_id: int, chroot: str, request: Request
) -> OkResponse:
    """Store a review submitted for a Copr build."""
    return _store_data_for_providers(
        feedback_input,
        ProvidersEnum.copr,
        build_id,
        chroot,
        our_server=_server_url(request),
    )


@router.post("/frontend/contribute/koji/{build_id}/{arch}")
def contribute_review_koji(
    feedback_input: FeedbackInputSchema, build_id: int, arch: str, request: Request
) -> OkResponse:
    """Store a review submitted for a Koji build."""
    return _store_data_for_providers(
        feedback_input,
        ProvidersEnum.koji,
        build_id,
        arch,
        our_server=_server_url(request),
    )


@router.post("/frontend/contribute/packit/{packit_id}")
def contribute_review_packit(
    feedback_input: FeedbackInputSchema, packit_id: int, request: Request
) -> OkResponse:
    """Store a review submitted for a Packit build."""
    return _store_data_for_providers(
        feedback_input, ProvidersEnum.packit, packit_id, our_server=_server_url(request)
    )


@router.post("/frontend/contribute/upload")
def contribute_upload_file(
    feedback_input: FeedbackInputSchema, request: Request
) -> OkResponse:
    """Store a review for uploaded build logs."""
    return _store_data_for_providers(
        feedback_input,
        ProvidersEnum.upload,
        int(datetime.now().timestamp()),
        our_server=_server_url(request),
    )


@router.post("/frontend/contribute/url/{url}")
def contribute_review_url(
    feedback_input: FeedbackInputSchema, url: str, request: Request
) -> OkResponse:
    """Store a review submitted for logs at a URL."""
    return _store_data_for_providers(
        feedback_input, ProvidersEnum.url, url, our_server=_server_url(request)
    )


@router.post("/frontend/contribute/container/{url}")
def contribute_review_container_logs(
    feedback_input: FeedbackInputSchema, url: str, request: Request
) -> OkResponse:
    """Store a review submitted for container logs."""
    return _store_data_for_providers(
        feedback_input, ProvidersEnum.container, url, our_server=_server_url(request)
    )


@router.post("/frontend/contribute/obs/{project}/{repository}/{architecture}/{package}")
def contribute_review_obs(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    feedback_input: FeedbackInputSchema,
    project: str,
    repository: str,
    architecture: str,
    package: str,
    request: Request,
) -> OkResponse:
    """Store a review submitted for an openSUSE Build Service package."""
    return _store_data_for_providers(
        feedback_input,
        ProvidersEnum.obs,
        f"{project}/{repository}/{architecture}/{package}",
        our_server=_server_url(request),
    )
