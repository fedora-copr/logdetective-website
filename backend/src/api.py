import json
import os
import uuid
from asyncio import create_task, gather
from base64 import b64decode
from contextlib import asynccontextmanager
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from typing import Optional
from urllib import parse

import httpx

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    FileResponse,
    RedirectResponse,
    PlainTextResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from src.constants import (
    COPR_BUILD_URL,
    KOJI_BUILD_URL,
    OBS_BUILD_URL,
    FEEDBACK_DIR,
    REVIEWS_DIR,
    SERVER_URL,
    LOGDETECTIVE_READ_TIMEOUT,
    LOGDETECTIVE_CONNECT_TIMEOUT,
    LOGDETECTIVE_DEFAULT_TIMEOUT,
    BuildIdTitleEnum,
    PROVIDER_COMMENTARY,
    ProvidersEnum,
    LOGGER_NAME,
    LOG_DETECTIVE_TOKEN,
    STATIC_SOURCE_DIR,
)
from src.fetcher import (
    ContainerProvider,
    CoprProvider,
    KojiProvider,
    OBSProvider,
    PackitProvider,
    URLProvider,
    RPMProvider,
    Provider,
)
from src.schema import (
    ContributeResponseSchema,
    FeedbackInputSchema,
    FeedbackSchema,
    FeedbackLogSchema,
    schema_inp_to_out,
)
from src.spells import (
    find_file_by_name,
    get_logger,
    start_sentry,
    read_json_file,
    write_json_file,
    fetch_text,
    sanitize_uploaded_schema,
    get_robots,
)
from src.store import Storator3000
from src.exceptions import NoDataFound
from src.client import get_http_client

LOGGER = get_logger(LOGGER_NAME)

# Attempt to initialize sentry and log the result
if start_sentry():
    LOGGER.info("Sentry initialized.")
else:
    LOGGER.warning("Sentry was not configured for this deployment.")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Manage application-wide resources."""
    _app.state.http_client = get_http_client()
    yield
    await _app.state.http_client.aclose()


app = FastAPI(
    title="Log Detective Website",
    lifespan=lifespan,
    contact={
        "name": "Log Detective developers",
        "url": "https://github.com/fedora-copr/logdetective-website",
        "email": "copr-devel@lists.fedorahosted.org",
    },
    license_info={
        "name": "Apache-2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
)


app.mount("/static", StaticFiles(directory=STATIC_SOURCE_DIR), name="static")
# blame scarlette for not being able to mount directories recursively
for root, directories, _ in os.walk(STATIC_SOURCE_DIR):
    for directory in directories:
        app.mount(
            f"/{directory}",
            StaticFiles(directory=os.path.join(root, directory)),
            name=directory,
        )

templates = Jinja2Templates(directory=STATIC_SOURCE_DIR)
template_response = templates.TemplateResponse


@app.exception_handler(Exception)
@app.exception_handler(HTTPException)
@app.exception_handler(RequestValidationError)
def _custom_http_exception_handler(
    request: Request, exc: HTTPException | RequestValidationError | Exception
) -> JSONResponse:
    if isinstance(exc, HTTPException):
        status_code = exc.status_code
    elif isinstance(exc, RequestValidationError):
        status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    else:
        status_code = HTTPStatus.INTERNAL_SERVER_ERROR

    if isinstance(exc, HTTPException):
        description = exc.detail
    else:
        description = str(exc)

    LOGGER.error("Exception %s encountered returing %s", exc, status_code)

    return JSONResponse(
        status_code=status_code,
        content={
            "error": f"Server error: {status_code}",
            "description": description,
        },
    )


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return template_response("index.html", {"request": request, "name": "app-homepage"})


@app.get("/contribute", response_class=HTMLResponse)
def contribute_landing(request: Request):
    """
    Submission dialog for log annotation contributions
    """
    mapping = {"name": "app-contribute-landing", "request": request}
    return template_response("app.html", mapping)


@app.get("/contribute/{args:path}", response_class=HTMLResponse)
def contribute(request: Request, args: str):
    # TODO: once ready for production, drop path and use proper paths
    _ = args
    mapping = {"name": "app-contribute", "request": request}
    return template_response("app.html", mapping)


@app.get("/documentation", response_class=HTMLResponse)
def documentation(request: Request):
    return template_response("documentation.html", {"request": request})


@app.get("/review", response_class=RedirectResponse)
def review_redirect():
    """
    Redirect to a review URL that contains some result ID
    """
    result = Storator3000.get_random()
    LOGGER.info("Opening %s for review", result)
    return f"/review/{result.stem}"


@app.get("/review/{result_id}", response_class=HTMLResponse)
def review(request: Request):
    mapping = {"name": "app-review", "request": request}
    return template_response("app.html", mapping)


@app.get("/explain/{args:path}", response_class=HTMLResponse)
@app.get("/explain", response_class=HTMLResponse)
def explain(request: Request, args: str = "", url: Optional[str] = None):
    # the URL is parsed by frontend, but having it mentioned here
    # means we have it documented
    _ = url
    _ = args
    mapping = {"name": "app-explain", "request": request}
    return template_response("app.html", mapping)


# Frontend API routes
# These are called from JavaScript to asynchronously fetch or post data


@app.get("/frontend/contribute/copr/{build_id}/{chroot}")
@app.get("/frontend/contribute/koji/{build_id}/{chroot}")
async def get_build_logs_with_chroot(
    request: Request, build_id: int, chroot: str
) -> ContributeResponseSchema:
    provider_name = request.url.path.lstrip("/").split("/")[2]
    prov_kls = CoprProvider if provider_name == ProvidersEnum.copr else KojiProvider
    provider = prov_kls(build_id, chroot, http_client=app.state.http_client)
    if provider_name == ProvidersEnum.copr:
        build_title = BuildIdTitleEnum.copr
        build_url = COPR_BUILD_URL.format(build_id)
    else:
        build_title = BuildIdTitleEnum.koji
        build_url = KOJI_BUILD_URL.format(build_id)

    return ContributeResponseSchema(
        build_id=build_id,
        build_id_title=build_title,
        build_url=build_url,
        logs=await provider.fetch_logs(),
        spec_file=await provider.fetch_spec_file(),
    )


@app.get("/frontend/contribute/packit/{packit_id}")
async def get_packit_build_logs(packit_id: int) -> ContributeResponseSchema:
    provider = PackitProvider(packit_id, http_client=app.state.http_client)
    return ContributeResponseSchema(
        build_id=packit_id,
        build_id_title=BuildIdTitleEnum.packit,
        build_url=await provider.get_url(),
        logs=await provider.fetch_logs(),
        spec_file=await provider.fetch_spec_file(),
    )


@app.get("/frontend/contribute/url/{base64}")
async def get_build_logs_from_url(base64: str) -> ContributeResponseSchema:
    build_url = b64decode(base64).decode("utf-8")
    provider = URLProvider(build_url, http_client=app.state.http_client)
    return ContributeResponseSchema(
        build_id=None,
        build_id_title=BuildIdTitleEnum.url,
        build_url=build_url,
        logs=await provider.fetch_logs(),
        spec_file=await provider.fetch_spec_file(),
    )


@app.get("/frontend/contribute/container/{base64}")
async def get_logs_from_container(base64: str) -> ContributeResponseSchema:
    build_url = b64decode(base64).decode("utf-8")
    provider = ContainerProvider(build_url, http_client=app.state.http_client)
    return ContributeResponseSchema(
        build_id=None,
        build_id_title=BuildIdTitleEnum.container,
        build_url=build_url,
        logs=await provider.fetch_logs(),
    )


@app.get("/frontend/contribute/obs/{project}/{repository}/{architecture}/{package}")
async def get_obs_build_logs(
    project: str, repository: str, architecture: str, package: str
) -> ContributeResponseSchema:
    """Return logs and spec file for an OBS build."""
    provider = OBSProvider(
        project, repository, architecture, package, http_client=app.state.http_client
    )
    return ContributeResponseSchema(
        build_id=None,
        build_id_title=BuildIdTitleEnum.obs,
        build_url=OBS_BUILD_URL.format(project, package),
        logs=await provider.fetch_logs(),
        spec_file=await provider.fetch_spec_file(),
    )


# TODO: some reasonable ok response would be better
class OkResponse(BaseModel):
    """Response on successful annotation submission, containing sumbission id and relative URLs
    pointing to posted annotation and review tooling.
    """

    status: str = "ok"
    review_id: str | uuid.UUID
    review_url_website: str
    review_url_json: str

    @staticmethod
    def from_id(id_: str | uuid.UUID, our_server: str) -> "OkResponse":
        """Constructs an OkResponse object from a review/contribution ID.

        Args:
            id (str | uuid.UUID): the review/contribution ID

        Returns:
            OkResponse: The OkResponse object with all required fields filled out.
        """
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

    if provider == ProvidersEnum.container:
        result_to_store = schema_inp_to_out(feedback_input, is_with_spec=False)
    else:
        result_to_store = schema_inp_to_out(feedback_input)

    sanitized_result_to_store = sanitize_uploaded_schema(result_to_store)
    contribution_id = storator.store(sanitized_result_to_store)
    if len(args) > 0:
        rest = f"/{args[0]}"
    else:
        rest = ""

    LOGGER.info(
        "Submitted data for %s: #%s(submission ID: %s) Additional args: %s",
        provider,
        id_,
        contribution_id,
        rest,
    )
    return OkResponse.from_id(contribution_id, our_server)


@app.post("/frontend/contribute/copr/{build_id}/{chroot}")
def contribute_review_copr(
    feedback_input: FeedbackInputSchema,
    build_id: int,
    chroot: str,
    request: Request,
) -> OkResponse:
    return _store_data_for_providers(
        feedback_input,
        ProvidersEnum.copr,
        build_id,
        chroot,
        our_server=f"{request.url.scheme}://{request.url.netloc}",
    )


@app.post("/frontend/contribute/koji/{build_id}/{arch}")
def contribute_review_koji(
    feedback_input: FeedbackInputSchema,
    build_id: int,
    arch: str,
    request: Request,
) -> OkResponse:
    return _store_data_for_providers(
        feedback_input,
        ProvidersEnum.koji,
        build_id,
        arch,
        our_server=f"{request.url.scheme}://{request.url.netloc}",
    )


@app.post("/frontend/contribute/packit/{packit_id}")
def contribute_review_packit(
    feedback_input: FeedbackInputSchema, packit_id: int, request: Request
) -> OkResponse:
    return _store_data_for_providers(
        feedback_input,
        ProvidersEnum.packit,
        packit_id,
        our_server=f"{request.url.scheme}://{request.url.netloc}",
    )


@app.post("/frontend/contribute/upload")
def contribute_upload_file(
    feedback_input: FeedbackInputSchema, request: Request
) -> OkResponse:
    dirname = int(datetime.now().timestamp())
    return _store_data_for_providers(
        feedback_input,
        ProvidersEnum.upload,
        dirname,
        our_server=f"{request.url.scheme}://{request.url.netloc}",
    )


@app.post("/frontend/contribute/url/{url}")
def contribute_review_url(
    feedback_input: FeedbackInputSchema, url: str, request: Request
) -> OkResponse:
    return _store_data_for_providers(
        feedback_input,
        ProvidersEnum.url,
        url,
        our_server=f"{request.url.scheme}://{request.url.netloc}",
    )


@app.post("/frontend/contribute/container/{url}")
def contribute_review_container_logs(
    feedback_input: FeedbackInputSchema, url: str, request: Request
) -> OkResponse:
    return _store_data_for_providers(
        feedback_input,
        ProvidersEnum.container,
        url,
        our_server=f"{request.url.scheme}://{request.url.netloc}",
    )


@app.post("/frontend/contribute/obs/{project}/{repository}/{architecture}/{package}")
# pylint: disable=too-many-arguments,too-many-positional-arguments
def contribute_review_obs(
    feedback_input: FeedbackInputSchema,
    project: str,
    repository: str,
    architecture: str,
    package: str,
    request: Request,
) -> OkResponse:
    """Contributor feedback for an OBS build log."""
    return _store_data_for_providers(
        feedback_input,
        ProvidersEnum.obs,
        f"{project}/{repository}/{architecture}/{package}",
        our_server=f"{request.url.scheme}://{request.url.netloc}",
    )


@app.get("/frontend/review/{result_id}")
def frontend_review_random(result_id):
    if result_id == "random":
        feedback_file = Storator3000.get_random()
    else:
        feedback_file = Storator3000.get_by_id(result_id)

    LOGGER.info("Opening annotation: %s for review", result_id)

    if not feedback_file:
        raise NoDataFound(f"No result with ID {result_id}")

    content = read_json_file(feedback_file)
    return FeedbackSchema(**content).model_dump() | {
        "id": feedback_file.name.rstrip(".json")
    }


async def _check_log_urls(
    log_urls: list[dict[str, str]], http_client: httpx.AsyncClient
) -> None:
    """Verify all log URLs are reachable using HEAD requests."""
    results = await gather(
        *(http_client.head(f["url"], timeout=10) for f in log_urls),
        return_exceptions=True,
    )
    unreachable = []
    for file_info, result in zip(log_urls, results):
        if isinstance(result, BaseException):
            unreachable.append((file_info["name"], file_info["url"], str(result)))
        elif result.status_code >= 400:
            unreachable.append(
                (file_info["name"], file_info["url"], str(result.status_code))
            )
    if unreachable:
        detail = "; ".join(
            f"{name} ({url}): {reason}" for name, url, reason in unreachable
        )
        LOGGER.error("Unreachable log URLs: %s", detail)
        raise HTTPException(status_code=422, detail=f"Unreachable log files: {detail}")


async def _call_analyze_api(
    log_urls: list[dict[str, str]],
    http_client: httpx.AsyncClient,
    spec_content: str | None = None,
    provider_name: Optional[str] = None,
) -> dict:
    """Send log URLs to the logdetective analyze API and return processed results."""
    commentary = ""
    if provider_name:
        commentary = PROVIDER_COMMENTARY.get(provider_name, "")

    LOGGER.info(
        "Log files to analyze: %s with commentary: %s",
        [(f["name"], f["url"]) for f in log_urls],
        commentary,
    )

    await _check_log_urls(log_urls, http_client=http_client)

    data = {
        "files": [{"name": f["name"], "url": f["url"]} for f in log_urls],
        "build_metadata": {
            "specfile": spec_content,
            "last_patch": None,
            "commentary": commentary,
            "infra_status": None,
        },
    }
    headers = {"Content-Type": "application/json"}

    if LOG_DETECTIVE_TOKEN:
        headers["Authorization"] = f"Bearer {LOG_DETECTIVE_TOKEN}"

    server_url = f"{SERVER_URL}/analyze"

    try:
        response = await http_client.post(
            server_url,
            headers=headers,
            json=data,
            timeout=httpx.Timeout(
                LOGDETECTIVE_DEFAULT_TIMEOUT,
                connect=LOGDETECTIVE_CONNECT_TIMEOUT,
                read=LOGDETECTIVE_READ_TIMEOUT,
            ),
        )
    except (httpx.ConnectError, httpx.TimeoutException) as ex:
        raise HTTPException(status_code=408, detail=str(ex)) from ex

    try:
        LOGGER.debug(
            "headers: %s data: %s", response.request.headers, response.request.content
        )
        response.raise_for_status()
    except httpx.HTTPError as ex:
        detail = f"{response.status_code} {response.reason_phrase}\n{response.url}"
        raise HTTPException(status_code=response.status_code, detail=detail) from ex

    return _process_server_data(response.content)


async def _explain_with_provider(
    provider: Provider, provider_name: str, http_client: httpx.AsyncClient
) -> dict:
    """Fetch log URLs, analyze them, fetch log content, return combined result."""

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


@app.post("/frontend/explain/")
async def frontend_explain_post(request: Request) -> dict:
    """Communicate with the logdetective server and process data.

    :returns: {
        "explanation": str,
        "extracted_snippets": [...],
        "logs": [{"name": str, "content": str}, ...]
    }
    """
    data = await request.json()
    log_url = data["prompt"]

    LOGGER.info("Asking server to analyze log '%s'", log_url)

    file_name = Path(parse.urlparse(url=log_url).path).name
    log_urls = [{"name": file_name, "url": log_url}]

    download_log_task = _download_log_content(log_url, client=app.state.http_client)
    analyze_task = _call_analyze_api(
        log_urls, provider_name=ProvidersEnum.url, http_client=app.state.http_client
    )

    result, log_data = await gather(analyze_task, download_log_task)

    result["logs"] = [{"name": file_name, "content": log_data}]

    return result


@app.post("/frontend/explain/copr/{build_id}/{chroot}")
async def explain_copr(build_id: int, chroot: str) -> dict:
    provider = CoprProvider(build_id, chroot, http_client=app.state.http_client)
    return await _explain_with_provider(
        provider, ProvidersEnum.copr, http_client=app.state.http_client
    )


@app.post("/frontend/explain/koji/{build_id}/{chroot}")
async def explain_koji(build_id: int, chroot: str) -> dict:
    provider = KojiProvider(build_id, chroot, http_client=app.state.http_client)
    return await _explain_with_provider(
        provider, ProvidersEnum.koji, http_client=app.state.http_client
    )


@app.post("/frontend/explain/packit/{packit_id}")
async def explain_packit(packit_id: int) -> dict:
    provider = PackitProvider(packit_id, http_client=app.state.http_client)
    return await _explain_with_provider(
        provider, ProvidersEnum.packit, http_client=app.state.http_client
    )


@app.post("/frontend/explain/url/{base64}")
async def explain_url(base64: str) -> dict:
    url = b64decode(base64).decode("utf-8")
    provider = URLProvider(url, http_client=app.state.http_client)
    return await _explain_with_provider(
        provider, ProvidersEnum.url, http_client=app.state.http_client
    )


@app.post("/frontend/explain/container/{base64}")
async def explain_container(base64: str) -> dict:
    url = b64decode(base64).decode("utf-8")
    provider = ContainerProvider(url, http_client=app.state.http_client)
    return await _explain_with_provider(
        provider, ProvidersEnum.container, http_client=app.state.http_client
    )


@app.post("/frontend/explain/obs/{project}/{repository}/{architecture}/{package}")
async def explain_obs(
    project: str, repository: str, architecture: str, package: str
) -> dict:
    """Forward an OBS build log to the logdetective server for explanation."""
    provider = OBSProvider(
        project, repository, architecture, package, http_client=app.state.http_client
    )
    return await _explain_with_provider(
        provider, ProvidersEnum.obs, http_client=app.state.http_client
    )


def _process_server_data(data) -> dict:
    """Process data received from logdetective server.

    Return them in format:
    {
        "explanation": str,
        "extracted_snippets": [
            {
                "snippet": str,
                "source_file": str,
                "line_number": int
            },
            ...
        ]
    }
    """
    try:
        parsed_data = json.loads(data)
    except json.JSONDecodeError as ex:
        raise HTTPException(
            status_code=500, detail="Received invalid data from server"
        ) from ex

    explanation = parsed_data["explanation"]["text"]
    extracted_snippets = []
    for snippet in parsed_data["snippets"]:
        extracted_snippets.append(
            {
                "snippet": snippet["text"],
                "source_file": snippet["source_file"],
                "line_number": snippet["line_number"],
            }
        )

    return {
        "explanation": explanation,
        "extracted_snippets": extracted_snippets,
    }


async def _download_log_content(url: str, client: httpx.AsyncClient) -> str:
    """Download content of the log file and returns it."""

    try:
        response = await fetch_text(url, client=client, timeout=600)
    except (
        httpx.ConnectError,
        httpx.TimeoutException,
        httpx.RequestError,
    ) as ex:
        raise HTTPException(status_code=408, detail=str(ex)) from ex
    try:
        response.raise_for_status()
    except httpx.HTTPError as ex:
        detail = f"{response.status_code} {response.reason_phrase}\n{response.url}"
        raise HTTPException(status_code=response.status_code, detail=detail) from ex

    return response.text


def _get_text_from_feedback(item: dict) -> str:
    if item["vote"] != 1:
        return ""

    return item["text"]


def _parse_logs(
    logs_orig: dict[str, FeedbackLogSchema], review_snippets: list[dict]
) -> None:
    for name, item in logs_orig.items():
        item.snippets = []
        for snippet in review_snippets:
            if snippet["file"] == name and snippet["vote"] == 1:
                # mypy can't see this far and hinting to it is messy
                item.snippets.append(snippet)  # type: ignore[arg-type]


def _parse_feedback(review_d: dict, origin_id: int) -> dict:
    original_file_path = find_file_by_name(f"{origin_id}.json", Path(FEEDBACK_DIR))
    if original_file_path is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"Original feedback file for ID {origin_id} not found",
        )

    original_content = read_json_file(original_file_path)
    schema = FeedbackSchema(**original_content)
    schema.fail_reason = _get_text_from_feedback(review_d["fail_reason"])
    schema.how_to_fix = _get_text_from_feedback(review_d["how_to_fix"])
    _parse_logs(schema.logs, review_d["snippets"])
    return schema.model_dump(exclude_unset=True)


@app.post("/frontend/review")
async def store_random_review(feedback_input: Request) -> OkResponse:
    """
    Store review from frontend.
    """
    # TODO: temporary silly solution until database is created
    #  (missing provider but we can dig it from original feedback file)
    reviews_dir = Path(REVIEWS_DIR)
    parsed_reviews_dir = reviews_dir / "parsed"
    parsed_reviews_dir.mkdir(parents=True, exist_ok=True)
    content = await feedback_input.json()
    original_file_id = content.pop("id")
    # avoid duplicates - same ID can be reviewed multiple times
    file_name = f"{original_file_id}-{int(datetime.now().timestamp())}"

    LOGGER.info("Storing review for %s as %s", original_file_id, file_name)

    write_json_file(
        reviews_dir / f"{file_name}.json",
        content | {"id": original_file_id},
    )

    parsed_feedback = _parse_feedback(content, original_file_id) | {
        "id": original_file_id
    }
    write_json_file(
        parsed_reviews_dir / f"{file_name}.json",
        parsed_feedback,
    )

    our_server = f"{feedback_input.url.scheme}://{feedback_input.url.netloc}"
    return OkResponse.from_id(file_name, our_server)


@app.get("/download")
def download_results():
    """
    Download all results we have as a tar.gz archive.

    The archive is pre-built daily by the create-archive CronJob and stored at
    /persistent/results-YYYY-MM-DD.tar.gz. This endpoint just serves the most
    recent one directly, avoiding a long blocking tar creation on each request.
    """
    if not FEEDBACK_DIR:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="No data found")

    storage_dir = Path(FEEDBACK_DIR).parent
    archives = sorted(
        [f for f in storage_dir.glob("results-*-*-*.tar.gz") if f.is_file()],
        reverse=True,
    )
    if not archives:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="No archive available yet, please try again later",
        )

    tar_path = archives[0]
    LOGGER.info("Starting download of the annotated dataset: %s", tar_path.name)

    # https://fastapi.tiangolo.com/advanced/custom-response/?h=fileresponse#fileresponse
    return FileResponse(
        tar_path,
        filename=tar_path.name,
    )


@app.get("/stats")
def get_report_stats() -> dict:
    """Produce basic information about submitted annotations."""
    LOGGER.info("Retrieving annotation statistics")

    return Storator3000.get_stats()


@app.get("/robots.txt", include_in_schema=False, response_class=PlainTextResponse)
def robots() -> str:
    """Return robots.txt"""
    return get_robots()
