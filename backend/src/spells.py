"""
Some random spells and helpers for backend :magic:
"""

import shutil
import tarfile
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def get_temporary_dir() -> Iterator[Path]:
    temp_dir = Path(tempfile.mkdtemp())
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir)


def make_tar(name: str, source: Path, destination: Path) -> Path:
    """
    Make tar from source path.

    Args:
        name: Name of the tar file
        source: Source to be tarred
        destination: Folder where to put tar file

    Returns:
        Path where to find a tar file.
    """
    tar_path = destination / name
    with tarfile.open(tar_path, "w:gz") as tar_f:
        tar_f.add(source, arcname=name)

    return tar_path
