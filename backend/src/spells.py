"""
Some random spells and helpers for backend :magic:
"""

import json
import logging
import os
import shutil
import tarfile
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

import requests
import sentry_sdk

from src.schema import (
    FeedbackSchema,
    NameContentSchema,
    FeedbackLogSchema,
)
from src.sanitization import (
    SchemaRedactionPipeline,
    SANITIZATION_PIPELINE,
)
from src.log_cleaning import (
    SNIPPET_LENGTH_THRESHOLD,
    snap_indexes_to_text,
    html_careful_unescape,
    log_schema_redaction,
)


@contextmanager
def get_temporary_dir() -> Iterator[Path]:
    temp_dir = Path(tempfile.mkdtemp())
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir)


def make_tar(name: str, sources: list[Path], destination: Path) -> Path:
    """
    Make tar from source path.

    Args:
        name: Name of the tar file
        sources: Sources to be tarred
        destination: Folder where to put tar file

    Returns:
        Path where to find a tar file.
    """
    tar_path = destination / name
    with tarfile.open(tar_path, "w:gz") as tar_f:
        for source in sources:
            tar_f.add(source, arcname=f"results/{source.name}")

    return tar_path


def find_file_by_name(name: str, path: Path) -> Optional[Path]:
    """
    Find file by name in the path.

    Args:
        name: Name of the file
        path: Path where to search
    """

    for file in path.rglob(name):
        if file.is_file():
            return file

    return None


def get_logger(logger_name: str):
    """Initialize a logger for this server"""
    log = logging.getLogger(logger_name)
    if getattr(log, "initialized", False):
        return log

    log.setLevel("DEBUG")

    # Drop the default handler, we will create it ourselves
    log.handlers = []

    # STDOUT
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
    stream_handler.setLevel("INFO")
    log.addHandler(stream_handler)

    log.initialized = True  # type: ignore
    return log


def start_sentry() -> bool:
    """Initializes sentry if the `SENTRY_SDN` is defined.
    Returns bool depending on service being initialized"""
    if sentry_dsn := os.environ.get("SENTRY_SDN"):
        sentry_sdk.init(dsn=sentry_dsn, traces_sample_rate=1.0)
        return True
    return False


def read_json_file(path: Path | str) -> Any:
    """
    Read JSON file with consistent UTF-8 encoding.

    Args:
        path: Path to the JSON file

    Returns:
        Parsed JSON content
    """
    with open(path, encoding="utf-8") as fp:
        return json.load(fp)


def write_json_file(path: Path | str, data: Any, indent: int = 4) -> None:
    """
    Write JSON file with consistent UTF-8 encoding.

    Uses ensure_ascii=False to preserve Unicode characters (like Czech diacritics)
    instead of escaping them to \\uXXXX sequences.

    Args:
        path: Path to the JSON file
        data: Data to serialize as JSON
        indent: Indentation level (default: 4)
    """
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=indent, ensure_ascii=False)


def read_text_file(path: Path | str) -> str:
    """
    Read text file with consistent UTF-8 encoding.

    Args:
        path: Path to the text file

    Returns:
        File content as string
    """
    with open(path, encoding="utf-8") as fp:
        return fp.read()


def fetch_text(url: str, **kwargs) -> requests.Response:
    """
    Fetch text content from URL with consistent UTF-8 encoding.

    Args:
        url: The URL to fetch
        **kwargs: Additional arguments passed to requests.get()

    Returns:
        requests.Response with encoding set to UTF-8
    """
    response = requests.get(url, **kwargs)
    response.encoding = "utf-8"
    return response


def ensure_text(content: str | bytes) -> str:
    """
    Ensure content is a UTF-8 decoded string.

    Args:
        content: String or bytes content

    Returns:
        UTF-8 decoded string
    """
    if isinstance(content, bytes):
        return content.decode("utf-8")
    return content


def clean_string(string: str, pipeline: SchemaRedactionPipeline) -> str:
    """
    Perform sanitization on a string (without adjusting indexes).
    """
    result = html_careful_unescape(string)
    for redaction in pipeline.steps:
        result = redaction.pattern.sub(redaction.replacement, result)
    return result


def clean_log_schema(log_schema: FeedbackLogSchema) -> FeedbackLogSchema:
    """
    Clean and sanitize a FeedbackLogSchema object by adding snippet texts,
    unescaping HTML entities, snapping snippet indexes to nearby newlines,
    and redacting personal information.

    Args:
        log_schema: The FeedbackLogSchema object to clean.
        pipeline: The SchemaRedactionPipeline containing redaction steps.

    Returns:
        The cleaned and sanitized FeedbackLogSchema object.
    """
    # 1) add snippet texts
    for snippet in log_schema.snippets:
        if snippet.text:
            continue
        if snippet.end_index == -1:
            snippet.end_index = len(log_schema.content)
        if snippet.start_index > snippet.end_index:
            snippet.start_index, snippet.end_index = (
                snippet.end_index,
                snippet.start_index,
            )
        if snippet.end_index - snippet.start_index < SNIPPET_LENGTH_THRESHOLD:
            continue
        snippet.text = log_schema.content[snippet.start_index : snippet.end_index]
    # 2) fix html escapes
    for snippet in log_schema.snippets:
        if snippet.text:
            snippet.text = clean_string(snippet.text, SANITIZATION_PIPELINE)
        snippet.user_comment = clean_string(snippet.user_comment, SANITIZATION_PIPELINE)
    log_schema.content = html_careful_unescape(log_schema.content)
    # 3) adjust indexes (let's use only ratio) + \n snapping
    snap_indexes_to_text(log_schema, ratio=0.02)
    # 4) redact personal info (with proper index adjustments)
    for step in SANITIZATION_PIPELINE.steps:
        log_schema.content = log_schema_redaction(
            log_schema.content, step, log_schema.snippets
        )
    return log_schema


def sanitize_uploaded_schema(input_schema: FeedbackSchema) -> FeedbackSchema:
    """
    Run sanitization on every viable string within a FeedbackSchema

    Args:
        input_schema: FeedbackSchema of a currently uploaded logs + snippets

    Returns:
        FeedbackSchema with sanitized/redacted personal data
    """

    sanitized_logs: dict[str, FeedbackLogSchema] = {
        name: clean_log_schema(schema) for name, schema in input_schema.logs.items()
    }

    result = FeedbackSchema(
        fail_reason=clean_string(input_schema.fail_reason, SANITIZATION_PIPELINE),
        how_to_fix=clean_string(input_schema.how_to_fix, SANITIZATION_PIPELINE),
        logs=sanitized_logs,
    )
    if isinstance(input_schema.spec_file, NameContentSchema):
        result.spec_file = NameContentSchema(
            name=input_schema.spec_file.name,
            content=clean_string(input_schema.spec_file.content, SANITIZATION_PIPELINE),
        )
    if isinstance(input_schema.container_file, NameContentSchema):
        result.container_file = NameContentSchema(
            name=input_schema.container_file.name,
            content=clean_string(
                input_schema.container_file.content, SANITIZATION_PIPELINE
            ),
        )

    return result
