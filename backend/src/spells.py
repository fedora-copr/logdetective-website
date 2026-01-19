"""
Some random spells and helpers for backend :magic:
"""

import shutil
import tarfile
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional
import logging
import os
import sentry_sdk

from src.schema import (
    FeedbackSchema,
    NameContentSchema,
    FeedbackLogSchema,
    SnippetSchema,
)
from src.sanitization import sanitize_string


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


def sanitize_uploaded_log(input_schema: FeedbackSchema) -> FeedbackSchema:
    """
    Run sanitization on every viable string within a FeedbackSchema

    Args:
        input_schema: FeedbackSchema of a currently uploaded logs + snippets

    Returns:
        FeedbackSchema with sanitized/redacted personal data
    """
    sanitized_logs = {}
    for logname, logschema in input_schema.logs.items():
        new_content = sanitize_string(logschema.name, logschema.content)
        new_snippets = [
            SnippetSchema(
                start_index=snip.start_index,
                end_index=snip.end_index,
                user_comment=sanitize_string("", snip.user_comment),
                text=sanitize_string("", snip.text) if snip.text is not None else None,
            )
            for snip in logschema.snippets
        ]
        sanitized_logs[logname] = FeedbackLogSchema(
            name=logschema.name, content=new_content, snippets=new_snippets
        )

    result = FeedbackSchema(
        logs=sanitized_logs,
        fail_reason=sanitize_string("", input_schema.fail_reason),
        how_to_fix=sanitize_string("", input_schema.how_to_fix),
    )
    if input_schema.spec_file is not None:
        result.spec_file = NameContentSchema(
            name=input_schema.spec_file.name,
            content=sanitize_string(
                input_schema.spec_file.name, input_schema.spec_file.content
            ),
        )
    if input_schema.container_file is not None:
        result.container_file = NameContentSchema(
            name=input_schema.container_file.name,
            content=sanitize_string(
                input_schema.container_file.name, input_schema.container_file.content
            ),
        )

    return result
