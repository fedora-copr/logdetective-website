"""Helper functions for /explain endpoints -- Log Detective analysis service."""

import json
from asyncio import gather, sleep, timeout
from contextlib import contextmanager
from http import HTTPStatus
from urllib import parse

import httpx
from fastapi import HTTPException

from src.constants import (
    LOG_DETECTIVE_TOKEN,
    LOGDETECTIVE_CONNECT_TIMEOUT,
    LOGDETECTIVE_DEFAULT_TIMEOUT,
    LOGDETECTIVE_READ_TIMEOUT,
    LOGGER_NAME,
    PROVIDER_COMMENTARY,
    SERVER_URL,
)
from src.spells import fetch_text, get_logger

LOGGER = get_logger(LOGGER_NAME)


async def _check_log_urls(
    log_urls: list[dict[str, str]], http_client: httpx.AsyncClient
) -> None:
    """Verify all log URLs are reachable using HEAD requests."""
    results = await gather(
        *(http_client.head(file_info["url"], timeout=10) for file_info in log_urls),
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


def _extract_error_detail_from_response(response: httpx.Response) -> str:
    """Extract and log error detail from an analysis-service response."""
    try:
        server_detail = response.json().get("detail", response.text)
    except (json.JSONDecodeError, ValueError, AttributeError):
        server_detail = response.text
    LOGGER.error("Analysis server error %s: %s", response.status_code, server_detail)
    return f"{response.status_code} {response.reason_phrase}\n{response.url}\n{server_detail}"


@contextmanager
def handle_httpx_errors():
    """Translate HTTP client errors into API responses."""
    try:
        yield
    except httpx.TimeoutException as ex:
        raise HTTPException(
            status_code=HTTPStatus.GATEWAY_TIMEOUT,
            detail=f"Request to analysis server timed out: {ex}",
        ) from ex
    except httpx.RequestError as ex:
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail=f"Could not connect to analysis server: {ex}",
        ) from ex
    except httpx.HTTPStatusError as ex:
        raise HTTPException(
            status_code=ex.response.status_code,
            detail=_extract_error_detail_from_response(ex.response),
        ) from ex


async def _poll_for_analysis_task(
    task_url: str,
    polling_timeout: float,
    http_client: httpx.AsyncClient,
    headers: dict,
    request_timeout: httpx.Timeout,
) -> dict | None:
    """Poll an analysis task and return its completed result, if ready."""
    await sleep(polling_timeout)
    with handle_httpx_errors():
        task_response = await http_client.get(
            task_url, headers=headers, timeout=request_timeout
        )
        task_response.raise_for_status()
    try:
        task = task_response.json()
        if not isinstance(task, dict):
            raise TypeError("task response is not an object")
        status = task["status"]
    except (KeyError, TypeError, ValueError) as ex:
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail="Analysis server returned an invalid task response",
        ) from ex
    if status in {"scheduled", "in_progress", "cancelling"}:
        return None
    if status == "done":
        return _process_server_data(task.get("result"))
    if status == "error":
        try:
            error_message = task["error"]["message"]
        except (KeyError, TypeError, ValueError) as ex:
            raise HTTPException(
                status_code=HTTPStatus.BAD_GATEWAY,
                detail="Analysis server returned an invalid task error response",
            ) from ex
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail=f"Analysis failed: {error_message}",
        )
    if status == "cancelled":
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY, detail="Analysis task was cancelled"
        )
    raise HTTPException(
        status_code=HTTPStatus.BAD_GATEWAY,
        detail=f"Analysis server returned unknown task status: {status}",
    )


async def _call_analyze_api(
    log_urls: list[dict[str, str]],
    http_client: httpx.AsyncClient,
    spec_content: str | None = None,
    provider_name: str | None = None,
) -> dict:
    """Send log URLs to the analysis API and return processed results."""
    commentary = PROVIDER_COMMENTARY.get(provider_name, "") if provider_name else ""
    LOGGER.info(
        "Log files to analyze: %s with commentary: %s",
        [(file_info["name"], file_info["url"]) for file_info in log_urls],
        commentary,
    )
    await _check_log_urls(log_urls, http_client=http_client)
    data = {
        "files": [
            {"name": file_info["name"], "url": file_info["url"]}
            for file_info in log_urls
        ],
        "build_metadata": {
            "specfile": spec_content,
            "last_patch": None,
            "commentary": commentary,
            "infra_status": None,
        },
    }
    request_headers = {"Content-Type": "application/json"}
    if LOG_DETECTIVE_TOKEN:
        request_headers["Authorization"] = f"Bearer {LOG_DETECTIVE_TOKEN}"
    request_timeout = httpx.Timeout(
        LOGDETECTIVE_DEFAULT_TIMEOUT,
        connect=LOGDETECTIVE_CONNECT_TIMEOUT,
    )
    with handle_httpx_errors():
        response = await http_client.post(
            f"{SERVER_URL}/analyze",
            headers=request_headers,
            json=data,
            timeout=request_timeout,
        )
        LOGGER.debug(
            "headers: %s data: %s", response.request.headers, response.request.content
        )
        if response.status_code != HTTPStatus.ACCEPTED:
            response.raise_for_status()
            raise HTTPException(
                status_code=HTTPStatus.BAD_GATEWAY,
                detail="Analysis server did not accept the analysis task",
            )
    try:
        task_url = str(response.headers["Location"])
        polling_timeout = float(response.headers.get("Retry-After", 5))
    except (KeyError, ValueError) as ex:
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail="Analysis server returned invalid task headers",
        ) from ex
    try:
        async with timeout(LOGDETECTIVE_READ_TIMEOUT):
            while True:
                result = await _poll_for_analysis_task(
                    task_url,
                    polling_timeout,
                    http_client,
                    request_headers,
                    request_timeout,
                )
                if result is not None:
                    return result
    except TimeoutError as ex:
        task_id = parse.urlparse(task_url).path.rstrip("/").rsplit("/", 1)[-1]
        raise HTTPException(
            status_code=HTTPStatus.GATEWAY_TIMEOUT,
            detail=(
                f"Timed out waiting for analysis task {task_id} after "
                f"{LOGDETECTIVE_READ_TIMEOUT} seconds"
            ),
        ) from ex


def _process_server_data(data) -> dict:
    """Convert an analysis-service task result to the frontend response shape."""
    try:
        parsed_data = json.loads(data) if isinstance(data, (bytes, str)) else data
        explanation = parsed_data["explanation"]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as ex:
        LOGGER.error("Invalid response from Log Detective server: %s", ex)
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail="Could not obtain explanation from the server's response.",
        ) from ex
    try:
        snippets = parsed_data.get("snippets") or []
        extracted_snippets = [
            {
                "snippet": snippet["text"],
                "source_file": snippet["source_file"],
                "line_number": snippet["line_number"],
            }
            for snippet in snippets
        ]
    except (AttributeError, KeyError, TypeError) as ex:
        LOGGER.error("Invalid response from Log Detective server: %s", ex)
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail="Could not obtain snippet data from the server's response.",
        ) from ex
    return {"explanation": explanation, "extracted_snippets": extracted_snippets}


async def _download_log_content(url: str, client: httpx.AsyncClient) -> str:
    """Download a log file for display with its analysis."""
    try:
        response = await fetch_text(url, client=client)
    except httpx.TimeoutException as ex:
        raise HTTPException(
            status_code=HTTPStatus.GATEWAY_TIMEOUT,
            detail=f"Request to download log file timed out: {ex}",
        ) from ex
    except httpx.RequestError as ex:
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail=f"Could not connect to log file URL: {ex}",
        ) from ex
    try:
        response.raise_for_status()
    except httpx.HTTPError as ex:
        raise HTTPException(
            status_code=response.status_code,
            detail=_extract_error_detail_from_response(response),
        ) from ex
    return response.text
