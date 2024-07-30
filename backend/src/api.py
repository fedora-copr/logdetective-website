import json
import logging
import os
from base64 import b64decode
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from typing import Iterator

from fastapi import FastAPI, Request, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from src.constants import (
    COPR_BUILD_URL,
    KOJI_BUILD_URL,
    FEEDBACK_DIR,
    REVIEWS_DIR,
    BuildIdTitleEnum,
    ProvidersEnum,
)
from src.fetcher import (
    ContainerProvider,
    CoprProvider,
    KojiProvider,
    PackitProvider,
    URLProvider,
    fetch_debug_logs,
)
from src.schema import (
    ContributeResponseSchema,
    FeedbackInputSchema,
    FeedbackSchema,
    FeedbackLogSchema,
    schema_inp_to_out,
)
from src.spells import make_tar, get_temporary_dir, find_file_by_name
from src.store import Storator3000

logger = logging.getLogger(__name__)

app = FastAPI()

# TODO: use absolute path perhaps?
template_dir = "../../frontend/public"
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


@app.get("/documentation", response_class=HTMLResponse)
def documentation(request: Request):
    return template_response("documentation.html", {"request": request})


@app.get("/review", response_class=HTMLResponse)
def review(request: Request):
    return template_response("review.html", {"request": request})


# Frontend API routes
# These are called from JavaScript to asynchronously fetch or post data


@app.get("/frontend/contribute/copr/{build_id}/{chroot}")
@app.get("/frontend/contribute/koji/{build_id}/{chroot}")
def get_build_logs_with_chroot(
    request: Request, build_id: int, chroot: str
) -> ContributeResponseSchema:
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
        build_url=provider.url,
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


@app.get("/frontend/contribute/container/{base64}")
def get_logs_from_container(base64: str) -> ContributeResponseSchema:
    build_url = b64decode(base64).decode("utf-8")
    provider = ContainerProvider(build_url)
    return ContributeResponseSchema(
        build_id=None,
        build_id_title=BuildIdTitleEnum.container,
        build_url=build_url,
        logs=provider.fetch_logs(),
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
    feedback_input: FeedbackInputSchema, provider: str, id_: int | str, *args
) -> OkResponse:
    storator = Storator3000(ProvidersEnum[provider], id_)

    if provider == ProvidersEnum.container:
        result_to_store = schema_inp_to_out(feedback_input, is_with_spec=False)
    else:
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


@app.post("/frontend/contribute/upload")
def contribute_upload_file(feedback_input: FeedbackInputSchema) -> OkResponse:
    dirname = int(datetime.now().timestamp())
    return _store_data_for_providers(feedback_input, ProvidersEnum.upload, dirname)


@app.post("/frontend/contribute/url/{url}")
def contribute_review_url(feedback_input: FeedbackInputSchema, url: str) -> OkResponse:
    return _store_data_for_providers(feedback_input, ProvidersEnum.url, url)


@app.post("/frontend/contribute/container/{url}")
def contribute_review_container_logs(
    feedback_input: FeedbackInputSchema, url: str
) -> OkResponse:
    return _store_data_for_providers(feedback_input, ProvidersEnum.container, url)


@app.get("/frontend/review/random")
def frontend_review_random():
    random_feedback_file = Storator3000.get_random()
    with open(random_feedback_file) as random_file:
        content = json.loads(random_file.read())
        return FeedbackSchema(**content).dict() | {"id": random_feedback_file.name.rstrip(".json")}


def _get_text_from_feedback(item: dict) -> str:
    if item["vote"] != 1:
        return ""

    return item["text"]


def _parse_snippet(snippet: dict) -> dict:
    return {
        "start_index": snippet["start-index"],
        "end_index": snippet["end-index"],
        "user_comment": snippet["comment"],
        "text": snippet["text"],
    }


def _parse_logs(logs_orig: dict[str, FeedbackLogSchema], review_snippets: list[dict]) -> None:
    for name, item in logs_orig.items():
        item.snippets = []
        for snippet in review_snippets:
            if snippet["file"] == name and snippet["vote"] == 1:
                # mypy can't see this far and hinting to it is messy
                item.snippets.append(_parse_snippet(snippet))  # type: ignore[arg-type]


def _parse_feedback(review_d: dict, origin_id: int) -> FeedbackSchema:
    original_file_path = find_file_by_name(f"{origin_id}.json", Path(FEEDBACK_DIR))
    if original_file_path is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"Original feedback file for ID {origin_id} not found",
        )

    with open(original_file_path, encoding="utf-8") as fp:
        original_content = json.load(fp)
        schema = FeedbackSchema(**original_content)
        # no reason to store username
        schema.username = None
        schema.fail_reason = _get_text_from_feedback(review_d["fail_reason"])
        schema.how_to_fix = _get_text_from_feedback(review_d["how_to_fix"])
        _parse_logs(schema.logs, review_d["snippets"])
        return schema.dict(exclude_unset=True)


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
    with open(reviews_dir / f"{file_name}.json", "w", encoding="utf-8") as fp:
        json.dump(content | {"id": original_file_id}, fp, indent=4)

    with open(parsed_reviews_dir / f"{file_name}.json", "w") as fp:
        json.dump(
            _parse_feedback(content, original_file_id) | {"id": original_file_id},
            fp,
            indent=4
        )

    return OkResponse()


def _make_tpm_tar_file_from_results() -> Iterator[Path]:
    if not FEEDBACK_DIR:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="No data found")

    with get_temporary_dir() as tmp_dir:
        tar_path = make_tar(
            f"results-{int(datetime.now().timestamp())}.tar.gz", Path(FEEDBACK_DIR), tmp_dir
        )
        try:
            yield tar_path
        finally:
            os.unlink(tar_path)


@app.get("/download", response_class=StreamingResponse)
def download_results(_tar_path=Depends(_make_tpm_tar_file_from_results)):
    def iter_large_file(file_name: Path):
        with open(file_name, mode="rb") as file:
            yield from file

    return StreamingResponse(
        iter_large_file(_tar_path),
        media_type="application/x-tar",
        headers={
            "Content-Disposition": f"attachment; filename={_tar_path.name}",
            "Content-Length": str(_tar_path.stat().st_size),
        },
    )


@app.get("/stats")
def get_report_stats() -> dict:
    return Storator3000.get_stats()
