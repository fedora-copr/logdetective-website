#!/usr/bin/python3
"""
This script takes data from local folder logjuicer-data, creates
a dataset out of it and pushes it to huggingface.

You need to have access to the HF dataset repo.
Set HF_TOKEN env var to be able to push

Create the data set using script logjuicer-dataset-create.py
"""
from pathlib import Path

from datasets import Dataset
import os


LOCAL_DIR = Path("./logjuicer-data")
LOG_NAMES = ("root.log", "build.log")
FILE_PREFIXES_MAPPING = {"": "original", "logjuicer-": "extract"}

final_data = []


def load_file_content(dir: Path, path: str) -> str:
    f = dir / path
    try:
        content = f.read_text()
    except FileNotFoundError:
        print(f"{f} does not exist")
        return ""
    if content:
        return content
    else:
        print(f"{f} is empty")
        return ""


for build_dir in LOCAL_DIR.iterdir():
    for logname in LOG_NAMES:
        payload = {}

        keyname = ""
        if content := load_file_content(build_dir, f"{keyname}{logname}"):
            payload[FILE_PREFIXES_MAPPING[keyname]] = content
        else:
            continue

        keyname = "logjuicer-"
        if content := load_file_content(build_dir, f"{keyname}{logname}"):
            payload[FILE_PREFIXES_MAPPING[keyname]] = content
        else:
            continue

        final_data.append(payload)
        print(f"{build_dir.name}: Full: {len(payload['original'])}"
              f" LJ: {len(payload['extract'])}")

dataset = Dataset.from_list(final_data)
dataset.push_to_hub('fedora-copr/logdetective-logjuicer-extract',
                    token=os.getenv('HF_TOKEN'))
