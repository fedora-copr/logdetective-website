import json
import logging
import os
from base64 import b64decode
from typing import Type

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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
    Provider,
    URLProvider,
    fetch_debug_logs,
)
from backend.schema import (
    BuildLogsSchema,
    ResultInputSchema,
    ResultSchema,
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
    "/frontend/contribute/copr/{build_id}/{chroot}", response_model=BuildLogsSchema
)
@app.get(
    "/frontend/contribute/koji/{build_id}/{chroot}", response_model=BuildLogsSchema
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
    }


@app.get("/frontend/contribute/packit/{packit_id}", response_model=BuildLogsSchema)
def get_packit_build_logs(packit_id: int):
    provider = PackitProvider(packit_id)
    return {
        "build_id": packit_id,
        "build_id_title": BuildIdTitleEnum.packit,
        "build_url": PACKIT_BUILD_URL,
        "logs": provider.fetch_logs(),
    }


@app.get("/frontend/contribute/url/{base64}", response_model=BuildLogsSchema)
def get_build_logs_from_url(base64: str):
    build_url = b64decode(base64).decode("utf-8")
    provider = URLProvider(build_url)
    return {
        "build_id": None,
        "build_id_title": BuildIdTitleEnum.url,
        "build_url": build_url,
        "logs": provider.fetch_logs(),
    }


# TODO: no response checking here, it will be deleted anyway
@app.get("/frontend/contribute/debug")
def get_debug_build_logs():
    return {
        "build_id": 123456,
        "build_id_title": BuildIdTitleEnum.debug,
        "build_url": "#",
        "logs": fetch_debug_logs(),
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


# TODO: split urls for args or use enums
@app.post("/frontend/contribute/{provider}/{args:path}")
def frontend_contribute_post(
    request: ResultInputSchema, provider: ProvidersEnum, args: str
):
    args_list = args.split("/")
    storator = Storator3000(provider, args_list[0])
    provider_kls = _get_provider_cls(provider)(*args_list)
    result_to_store = schema_inp_to_out(request, provider_kls.fetch_spec_file())
    storator.store(result_to_store)

    # TODO: parse args_list for url and packit
    if len(args_list) > 1:
        chroot_info = args_list[1]
    else:
        chroot_info = "unknown arch"
    logger.info(
        "Submitted data for {%s}: #{%s/%s}", provider, args_list[0], chroot_info
    )
    return {"status": "ok"}


@app.get("/frontend/review", response_model=ResultSchema)
def frontend_review():
    random_feedback_file = Storator3000.get_random()
    with open(random_feedback_file) as random_file:
        # FIXME: I converted dict to string before dumps...
        content = json.loads(json.loads(random_file.read()))
        return ResultSchema(**content)
