"""
Some random spells and helpers for backend :magic:
"""

import shutil
import tarfile
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional


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
