import json
import logging
import os
from base64 import b64decode
from typing import Type

from fastapi import FastAPI, Request
from fastapi.exceptions import FastAPIError, RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.constants import (
    COPR_BUILD_URL,
    KOJI_BUILD_URL,
    PACKIT_BUILD_URL,
    BuildIdTitleEnum,
    ProvidersEnum,
)
from backend.exceptions import HTTPException
from backend.fetcher import (
    CoprProvider,
    KojiProvider,
    PackitProvider,
    Provider,
    URLProvider,
    fetch_debug_logs,
)
from backend.schema import (
    ContributeResponseSchema,
    FeedbackInputSchema,
    FeedbackSchema,
    schema_inp_to_out,
)
from backend.store import Storator3000

logger = logging.getLogger(__name__)

app = FastAPI()

template_dir = "../frontend/public"
app.mount("/static", StaticFiles(directory=template_dir), name="static")
# blame scarlette for not being able to mount directories recursively
for root, directories, _ in os.walk(template_dir):
    for directory in directories:
        app.mount(
            f"/{directory}",
            StaticFiles(directory=os.path.join(root, directory)),
            name=directory,
        )

templates = Jinja2Templates(directory=template_dir)
template_response = templates.TemplateResponse


# TODO: handle all exceptions raised in fastapi here, ideally in one exception handler
@app.exception_handler(Exception)
@app.exception_handler(HTTPException)
@app.exception_handler(StarletteHTTPException)
@app.exception_handler(FastAPIError)
@app.exception_handler(RequestValidationError)
def _custom_http_exception_handler(
    request: Request, exc: HTTPException | StarletteHTTPException | Exception
):
    if isinstance(exc, (HTTPException, StarletteHTTPException)):
        status_code = exc.status_code
    else:
        # TODO: get it from RequestValidationError
        if isinstance(exc, RequestValidationError):
            status_code = 422
        else:
            status_code = 500

    if isinstance(exc, StarletteHTTPException):
        description = exc.detail
    else:
        description = str(exc)

    return JSONResponse(
        status_code=status_code,
        content={
            "error": f"Server error: {status_code}",
            "description": description,
        },
    )


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return template_response("index.html", {"request": request})


@app.get("/contribute/{args:path}", response_class=HTMLResponse)
def contribute(request: Request, args: str):
    # TODO: once ready for production, drop path and use proper paths
    _ = args
    return template_response("contribute.html", {"request": request})


@app.get("/review", response_class=HTMLResponse)
def review(request: Request):
    return template_response("review.html", {"request": request})


# Frontend API routes
# These are called from JavaScript to asynchronously fetch or post data


@app.get(
    "/frontend/contribute/copr/{build_id}/{chroot}",
    response_model=ContributeResponseSchema,
)
@app.get(
    "/frontend/contribute/koji/{build_id}/{chroot}",
    response_model=ContributeResponseSchema,
)
def get_build_logs_with_chroot(request: Request, build_id: int, chroot: str):
    provider_name = request.url.path.lstrip("/").split("/")[2]
    prov_kls = CoprProvider if provider_name == ProvidersEnum.copr else KojiProvider
    provider = prov_kls(build_id, chroot)
    if provider_name == ProvidersEnum.copr:
        build_title = BuildIdTitleEnum.copr
        build_url = COPR_BUILD_URL.format(build_id)
    else:
        build_title = BuildIdTitleEnum.koji
        build_url = KOJI_BUILD_URL.format(build_id)

    return {
        "build_id": build_id,
        "build_id_title": build_title,
        "build_url": build_url,
        "logs": provider.fetch_logs(),
        "spec_file": provider.fetch_spec_file(),
    }


@app.get(
    "/frontend/contribute/packit/{packit_id}", response_model=ContributeResponseSchema
)
def get_packit_build_logs(packit_id: int):
    provider = PackitProvider(packit_id)
    return {
        "build_id": packit_id,
        "build_id_title": BuildIdTitleEnum.packit,
        "build_url": PACKIT_BUILD_URL,
        "logs": provider.fetch_logs(),
        "spec_file": provider.fetch_spec_file(),
    }


@app.get("/frontend/contribute/url/{base64}", response_model=ContributeResponseSchema)
def get_build_logs_from_url(base64: str):
    build_url = b64decode(base64).decode("utf-8")
    provider = URLProvider(build_url)
    return {
        "build_id": None,
        "build_id_title": BuildIdTitleEnum.url,
        "build_url": build_url,
        "logs": provider.fetch_logs(),
        "spec_file": provider.fetch_spec_file(),
    }


# TODO: no response checking here, it will be deleted anyway
@app.get("/frontend/contribute/debug")
def get_debug_build_logs():
    return {
        "build_id": 123456,
        "build_id_title": BuildIdTitleEnum.debug,
        "build_url": "#",
        "logs": fetch_debug_logs(),
        "spec_file": "fake spec file",
    }


def _get_provider_cls(provider_enum: ProvidersEnum) -> Type[Provider]:
    hashmap = {
        ProvidersEnum.copr: CoprProvider,
        ProvidersEnum.koji: KojiProvider,
        ProvidersEnum.packit: PackitProvider,
        ProvidersEnum.url: URLProvider,
    }
    provider_cls = hashmap.get(provider_enum)
    if provider_cls is None:
        raise ValueError(f"Unknown provider: {provider_enum}")

    return provider_cls


# TODO: delete this once in production
@app.post("/frontend/contribute/debug")
def frontend_debug_contribute():
    logger.info("Debug data were fakely stored.")
    return {"status": "ok"}


def _store_data_for_providers(
    feedback_input: FeedbackInputSchema, provider: ProvidersEnum, id_: int | str, *args
) -> None:
    storator = Storator3000(provider, id_)
    result_to_store = schema_inp_to_out(feedback_input)
    storator.store(result_to_store)
    if len(args) > 0:
        rest = f"/{args[0]}"
    else:
        rest = ""

    logger.info("Submitted data for {%s}: #{%s}{%s}", provider, id_, rest)


@app.post("/frontend/contribute/copr/{build_id}/{chroot}")
def contribute_review_copr(
    feedback_input: FeedbackInputSchema, build_id: int, chroot: str
):
    _store_data_for_providers(feedback_input, ProvidersEnum.copr, build_id, chroot)
    return {"status": "ok"}


@app.post("/frontend/contribute/koji/{build_id}/{arch}")
def contribute_review_koji(
    feedback_input: FeedbackInputSchema, build_id: int, arch: str
):
    _store_data_for_providers(feedback_input, ProvidersEnum.koji, build_id, arch)
    return {"status": "ok"}


@app.post("/frontend/contribute/packit/{packit_id}")
def contribute_review_packit(feedback_input: FeedbackInputSchema, packit_id: int):
    _store_data_for_providers(feedback_input, ProvidersEnum.packit, packit_id)
    return {"status": "ok"}


@app.post("/frontend/contribute/url/{url}")
def contribute_review_url(feedback_input: FeedbackInputSchema, url: str):
    _store_data_for_providers(feedback_input, ProvidersEnum.url, url)
    return {"status": "ok"}


@app.get("/frontend/review", response_model=FeedbackSchema)
def frontend_review():
    if os.environ.get("ENV") == "production":
        raise NotImplementedError("Reviewing is not ready yet")

    random_feedback_file = Storator3000.get_random()
    with open(random_feedback_file) as random_file:
        content = json.loads(random_file.read())
        return FeedbackSchema(**content)
