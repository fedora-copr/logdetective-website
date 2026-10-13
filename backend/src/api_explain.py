"""Explanation API routes."""

from asyncio import create_task, gather
from base64 import b64decode
from pathlib import Path
from urllib import parse

import httpx
from fastapi import APIRouter, Request

from src.analysis import (
    _call_analyze_api,
    _download_log_content,
)
from src.constants import LOGGER_NAME, ProvidersEnum
from src.fetcher import (
    ContainerProvider,
    CoprProvider,
    KojiProvider,
    OBSProvider,
    PackitProvider,
    Provider,
    RPMProvider,
    URLProvider,
)
from src.spells import get_logger

LOGGER = get_logger(LOGGER_NAME)
router = APIRouter()


async def _explain_with_provider(
    provider: Provider, provider_name: str, http_client: httpx.AsyncClient
) -> dict:
    """Fetch provider data, analyze the logs, and combine the results."""
    LOGGER.info("Received request for analysis from: %s", provider_name)
    log_urls = await provider.fetch_log_urls()
    spec_content = None
    if isinstance(provider, RPMProvider):
        spec = await provider.fetch_spec_file()
        spec_content = spec["content"] if spec else None
    analyze_task = create_task(
        _call_analyze_api(
            log_urls,
            http_client=http_client,
            spec_content=spec_content,
            provider_name=provider_name,
        )
    )
    content_task = create_task(provider.fetch_logs())
    result, logs = await gather(analyze_task, content_task)
    result["logs"] = [{"name": log["name"], "content": log["content"]} for log in logs]
    return result


@router.post("/frontend/explain/")
async def frontend_explain_post(request: Request) -> dict:
    """Analyze a directly supplied log URL."""
    data = await request.json()
    log_url = data["prompt"]
    LOGGER.info("Asking server to analyze log '%s'", log_url)
    file_name = Path(parse.urlparse(url=log_url).path).name
    log_urls = [{"name": file_name, "url": log_url}]
    http_client = request.app.state.http_client
    result, log_data = await gather(
        _call_analyze_api(
            log_urls, provider_name=ProvidersEnum.url, http_client=http_client
        ),
        _download_log_content(log_url, client=http_client),
    )
    result["logs"] = [{"name": file_name, "content": log_data}]
    return result


@router.post("/frontend/explain/copr/{build_id}/{chroot}")
async def explain_copr(request: Request, build_id: int, chroot: str) -> dict:
    """Analyze logs from a Copr build."""
    client = request.app.state.http_client
    return await _explain_with_provider(
        CoprProvider(build_id, chroot, http_client=client), ProvidersEnum.copr, client
    )


@router.post("/frontend/explain/koji/{build_id}/{chroot}")
async def explain_koji(request: Request, build_id: int, chroot: str) -> dict:
    """Analyze logs from a Koji build."""
    client = request.app.state.http_client
    return await _explain_with_provider(
        KojiProvider(build_id, chroot, http_client=client), ProvidersEnum.koji, client
    )


@router.post("/frontend/explain/packit/{packit_id}")
async def explain_packit(request: Request, packit_id: int) -> dict:
    """Analyze logs from a Packit build."""
    client = request.app.state.http_client
    return await _explain_with_provider(
        PackitProvider(packit_id, http_client=client), ProvidersEnum.packit, client
    )


@router.post("/frontend/explain/url/{base64}")
async def explain_url(request: Request, base64: str) -> dict:
    """Analyze logs from a URL encoded as base64."""
    client = request.app.state.http_client
    url = b64decode(base64).decode("utf-8")
    return await _explain_with_provider(
        URLProvider(url, http_client=client), ProvidersEnum.url, client
    )


@router.post("/frontend/explain/container/{base64}")
async def explain_container(request: Request, base64: str) -> dict:
    """Analyze logs from a container URL encoded as base64."""
    client = request.app.state.http_client
    url = b64decode(base64).decode("utf-8")
    return await _explain_with_provider(
        ContainerProvider(url, http_client=client), ProvidersEnum.container, client
    )


@router.post("/frontend/explain/obs/{project}/{repository}/{architecture}/{package}")
async def explain_obs(
    request: Request, project: str, repository: str, architecture: str, package: str
) -> dict:
    """Forward an OBS build log to the analysis server."""
    client = request.app.state.http_client
    provider = OBSProvider(
        project, repository, architecture, package, http_client=client
    )
    return await _explain_with_provider(provider, ProvidersEnum.obs, client)
