import json
import logging
import os
from base64 import b64decode
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from backend.constants import (
    COPR_BUILD_URL,
    KOJI_BUILD_URL,
    PACKIT_BUILD_URL,
    BuildIdTitleEnum,
    ProvidersEnum,
)
from backend.fetcher import (
    CoprProvider,
    KojiProvider,
    PackitProvider,
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


@app.exception_handler(Exception)
@app.exception_handler(HTTPException)
@app.exception_handler(RequestValidationError)
def _custom_http_exception_handler(
    request: Request, exc: HTTPException | RequestValidationError | Exception
):
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


@app.get("/frontend/contribute/copr/{build_id}/{chroot}")
@app.get("/frontend/contribute/koji/{build_id}/{chroot}")
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

    return ContributeResponseSchema(
        build_id=build_id,
        build_id_title=build_title,
        build_url=build_url,
        logs=provider.fetch_logs(),
        spec_file=provider.fetch_spec_file(),
    )


@app.get("/frontend/contribute/packit/{packit_id}")
def get_packit_build_logs(packit_id: int) -> ContributeResponseSchema:
    provider = PackitProvider(packit_id)
    return ContributeResponseSchema(
        build_id=packit_id,
        build_id_title=BuildIdTitleEnum.packit,
        build_url=PACKIT_BUILD_URL,
        logs=provider.fetch_logs(),
        spec_file=provider.fetch_spec_file(),
    )


@app.get("/frontend/contribute/url/{base64}")
def get_build_logs_from_url(base64: str) -> ContributeResponseSchema:
    build_url = b64decode(base64).decode("utf-8")
    provider = URLProvider(build_url)
    return ContributeResponseSchema(
        build_id=None,
        build_id_title=BuildIdTitleEnum.url,
        build_url=build_url,
        logs=provider.fetch_logs(),
        spec_file=provider.fetch_spec_file(),
    )


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


# TODO: delete this once in production
@app.post("/frontend/contribute/debug")
def frontend_debug_contribute():
    logger.info("Debug data were fakely stored.")
    return {"status": "ok"}


# TODO: some reasonable ok response would be better
class OkResponse(BaseModel):
    status: str = "ok"


def _store_data_for_providers(
    feedback_input: FeedbackInputSchema, provider: ProvidersEnum, id_: int | str, *args
) -> OkResponse:
    storator = Storator3000(provider, id_)
    result_to_store = schema_inp_to_out(feedback_input)
    storator.store(result_to_store)
    if len(args) > 0:
        rest = f"/{args[0]}"
    else:
        rest = ""

    logger.info("Submitted data for {%s}: #{%s}{%s}", provider, id_, rest)
    return OkResponse()


@app.post("/frontend/contribute/copr/{build_id}/{chroot}")
def contribute_review_copr(
    feedback_input: FeedbackInputSchema, build_id: int, chroot: str
) -> OkResponse:
    return _store_data_for_providers(
        feedback_input, ProvidersEnum.copr, build_id, chroot
    )


@app.post("/frontend/contribute/koji/{build_id}/{arch}")
def contribute_review_koji(
    feedback_input: FeedbackInputSchema, build_id: int, arch: str
) -> OkResponse:
    return _store_data_for_providers(feedback_input, ProvidersEnum.koji, build_id, arch)


@app.post("/frontend/contribute/packit/{packit_id}")
def contribute_review_packit(
    feedback_input: FeedbackInputSchema, packit_id: int
) -> OkResponse:
    return _store_data_for_providers(feedback_input, ProvidersEnum.packit, packit_id)


@app.post("/frontend/contribute/url/{url}")
def contribute_review_url(feedback_input: FeedbackInputSchema, url: str) -> OkResponse:
    return _store_data_for_providers(feedback_input, ProvidersEnum.url, url)


@app.get("/frontend/review")
def frontend_review() -> FeedbackSchema:
    if os.environ.get("ENV") == "production":
        raise NotImplementedError("Reviewing is not ready yet")

    random_feedback_file = Storator3000.get_random()
    with open(random_feedback_file) as random_file:
        content = json.loads(random_file.read())
        return FeedbackSchema(**content)
