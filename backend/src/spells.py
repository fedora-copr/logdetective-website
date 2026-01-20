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
