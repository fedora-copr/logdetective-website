"""FastAPI application setup and small application-level routes."""

import os
from contextlib import asynccontextmanager
from datetime import date, datetime
from http import HTTPStatus
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.background import BackgroundTask
from starlette.exceptions import HTTPException

from src.api_contribute import OkResponse
from src.api_contribute import router as contribute_router
from src.api_explain import router as explain_router
from src.client import get_http_client
from src.constants import (
    DOWNLOAD_SINCE_MAX_DAYS,
    FEEDBACK_DIR,
    LOGGER_NAME,
    REVIEWS_DIR,
    STATIC_SOURCE_DIR,
)
from src.exceptions import NoDataFound
from src.schema import FeedbackLogSchema, FeedbackSchema
from src.spells import (
    build_filtered_archive,
    find_file_by_name,
    get_logger,
    get_robots,
    read_json_file,
    start_sentry,
    write_json_file,
)
from src.store import Storator3000

LOGGER = get_logger(LOGGER_NAME)

if start_sentry():
    LOGGER.info("Sentry initialized.")
else:
    LOGGER.warning("Sentry was not configured for this deployment.")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Manage application-wide resources."""
    Storator3000.ensure_directories()
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
    _request: Request, exc: HTTPException | RequestValidationError | Exception
) -> JSONResponse:
    if isinstance(exc, HTTPException):
        status_code, description = exc.status_code, exc.detail
    elif isinstance(exc, RequestValidationError):
        status_code = HTTPStatus.UNPROCESSABLE_ENTITY
        errors = exc.errors()
        description = (
            "\n".join(
                error.get("msg", f"Failed to fetch validation error #{index + 1}")
                for index, error in enumerate(errors)
            )
            if errors
            else "The submitted data was invalid."
        )
    else:
        status_code, description = HTTPStatus.INTERNAL_SERVER_ERROR, str(exc)
    LOGGER.error("Exception %s encountered returing %s", exc, status_code)
    return JSONResponse(status_code=status_code, content={"description": description})


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    """Render homepage."""
    return template_response("index.html", {"request": request, "name": "app-homepage"})


@app.get("/contribute", response_class=HTMLResponse)
def contribute_landing(request: Request):
    """Render the contribution landing page."""
    return template_response(
        "app.html", {"name": "app-contribute-landing", "request": request}
    )


@app.get("/contribute/{args:path}", response_class=HTMLResponse)
def contribute(request: Request, args: str):
    """Render a specific contribute page."""
    _ = args
    return template_response("app.html", {"name": "app-contribute", "request": request})


@app.get("/documentation", response_class=HTMLResponse)
def documentation(request: Request):
    """Render the documentation landing page."""
    return template_response("documentation.html", {"request": request})


@app.get("/review", response_class=RedirectResponse)
def review_redirect():
    """Redirect to a randomly selected review."""
    result = Storator3000.get_random()
    LOGGER.info("Opening %s for review", result)
    return f"/review/{result.stem}"


@app.get("/review/{result_id}", response_class=HTMLResponse)
def review(request: Request):
    """Render the review page for a specific result."""
    return template_response("app.html", {"name": "app-review", "request": request})


@app.get("/explain/{args:path}", response_class=HTMLResponse)
@app.get("/explain", response_class=HTMLResponse)
def explain(request: Request, args: str = "", url: str | None = None):
    """Render the log explanation page."""
    _ = args
    _ = url
    return template_response("app.html", {"name": "app-explain", "request": request})


@app.get("/frontend/review/{result_id}")
def frontend_review_random(result_id):
    """Return stored review data by ID, or select a random review."""
    feedback_file = (
        Storator3000.get_random()
        if result_id == "random"
        else Storator3000.get_by_id(result_id)
    )
    LOGGER.info("Opening annotation: %s for review", result_id)
    if not feedback_file:
        raise NoDataFound(f"No result with ID {result_id}")
    return FeedbackSchema(**read_json_file(feedback_file)).model_dump() | {
        "id": feedback_file.name.rstrip(".json")
    }


def _get_text_from_feedback(item: dict) -> str:
    return item["text"] if item["vote"] == 1 else ""


def _parse_logs(
    logs_orig: dict[str, FeedbackLogSchema], review_snippets: list[dict]
) -> None:
    for name, item in logs_orig.items():
        item.snippets = []
        for snippet in review_snippets:
            if snippet["file"] == name and snippet["vote"] == 1:
                item.snippets.append(snippet)  # type: ignore[arg-type]


def _parse_feedback(review_d: dict, origin_id: int) -> dict:
    original_file_path = find_file_by_name(f"{origin_id}.json", Path(FEEDBACK_DIR))
    if original_file_path is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"Original feedback file for ID {origin_id} not found",
        )
    schema = FeedbackSchema(**read_json_file(original_file_path))
    schema.fail_reason = _get_text_from_feedback(review_d["fail_reason"])
    schema.how_to_fix = _get_text_from_feedback(review_d["how_to_fix"])
    _parse_logs(schema.logs, review_d["snippets"])
    return schema.model_dump(exclude_unset=True)


@app.post("/frontend/review")
async def store_random_review(feedback_input: Request) -> OkResponse:
    """Store submitted review data and return its public URLs."""
    reviews_dir = Path(REVIEWS_DIR)
    parsed_reviews_dir = reviews_dir / "parsed"
    parsed_reviews_dir.mkdir(parents=True, exist_ok=True)
    content = await feedback_input.json()
    original_file_id = content.pop("id")
    file_name = f"{original_file_id}-{int(datetime.now().timestamp())}"
    LOGGER.info("Storing review for %s as %s", original_file_id, file_name)
    write_json_file(
        reviews_dir / f"{file_name}.json", content | {"id": original_file_id}
    )
    write_json_file(
        parsed_reviews_dir / f"{file_name}.json",
        _parse_feedback(content, original_file_id) | {"id": original_file_id},
    )
    return OkResponse.from_id(
        file_name, f"{feedback_input.url.scheme}://{feedback_input.url.netloc}"
    )


def _validated_since(since: date | None = None) -> date | None:
    if since is not None and (date.today() - since).days > DOWNLOAD_SINCE_MAX_DAYS:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"The 'since' date must be within the last {DOWNLOAD_SINCE_MAX_DAYS} days",
        )
    return since


@app.get("/download")
def download_results(since: Annotated[date | None, Depends(_validated_since)]):
    """Download the annotated dataset, optionally filtered by date."""
    if not FEEDBACK_DIR:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="No data found")
    if since is not None:
        archive_path = build_filtered_archive(FEEDBACK_DIR, since)
        if archive_path is None:
            return Response(status_code=HTTPStatus.NO_CONTENT)
        filename = f"results-since-{since.isoformat()}.tar.gz"
        LOGGER.info("Serving filtered dataset archive: %s", filename)
        return FileResponse(
            archive_path,
            filename=filename,
            background=BackgroundTask(os.unlink, archive_path),
        )
    archives = sorted(
        [
            archive
            for archive in Path(FEEDBACK_DIR).parent.glob("results-*-*-*.tar.gz")
            if archive.is_file()
        ],
        reverse=True,
    )
    if not archives:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="No archive available yet, please try again later",
        )
    tar_path = archives[0]
    LOGGER.info("Starting download of the annotated dataset: %s", tar_path.name)
    return FileResponse(tar_path, filename=tar_path.name)


@app.get("/stats")
def get_report_stats() -> dict:
    """Return statistics about stored annotations."""
    LOGGER.info("Retrieving annotation statistics")
    return Storator3000.get_stats()


@app.get("/robots.txt", include_in_schema=False, response_class=PlainTextResponse)
def robots() -> str:
    """Return the site's robots.txt contents."""
    return get_robots()


app.include_router(contribute_router)
app.include_router(explain_router)
