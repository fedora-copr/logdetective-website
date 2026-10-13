#!/usr/bin/env python3
"""
Create a dated tar.gz archive of all feedback and review data in STORAGE_DIR.
Intended to be run daily via a Kubernetes CronJob.
"""

import os
import tarfile
from datetime import date
from pathlib import Path

FEEDBACK_DIR = Path(os.environ.get("FEEDBACK_DIR", "/persistent/results"))
REVIEWS_DIR = Path(os.environ.get("REVIEWS_DIR", "/persistent/reviews"))


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
    tmp_path = destination / f"tmp-{name}"
    tar_path = destination / name
    with tarfile.open(tmp_path, "w:gz") as tar_f:
        for source in sources:
            if source.exists():
                tar_f.add(source, arcname=f"results/{source.name}")
            else:
                print(f"{source} not found, skipping this source.")
    tmp_path.rename(tar_path)
    return tar_path


def main():
    """Create a dated tar.gz archive of feedback and review data, removing any older ones."""
    storage_dir = FEEDBACK_DIR.parent
    tar_name = f"results-{date.today().isoformat()}.tar.gz"
    tar_path = make_tar(tar_name, [FEEDBACK_DIR, REVIEWS_DIR], storage_dir)
    print(f"Archive created: {tar_path}")

    for old in storage_dir.glob("results-*-*-*.tar.gz"):
        if old != tar_path:
            old.unlink()
            print(f"Removed old archive: {old}")


if __name__ == "__main__":
    main()
