#!/bin/env python
# You need to have access to the HF dataset repo
# Set it in the HF_TOKEN env var

from datasets import load_dataset
import json
import glob
import requests
import tarfile
import tempfile
import os
import shutil

LOG_DETECTIVE_DOWNLOAD_API = "https://www.logdetective.com/download"
LOG_DETECTIVE_DATA_FILE = "log_detective_data.tar.gz"
EXTRACTION_DIR = 'log_detective_data'

r = requests.get(LOG_DETECTIVE_DOWNLOAD_API, stream=True)

tmp_dir = tempfile.mkdtemp("_log_detective")

with open(os.path.join(tmp_dir, LOG_DETECTIVE_DATA_FILE), 'wb') as fd:
    for chunk in r.iter_content(chunk_size=128):
        fd.write(chunk)

print("Reports from Log Detective downloaded")

try:
    with tarfile.open(os.path.join(tmp_dir, LOG_DETECTIVE_DATA_FILE), mode='r:gz') as f:
        f.extractall(os.path.join(tmp_dir, EXTRACTION_DIR))

    data = []

    for file in glob.glob(f"{os.path.join(tmp_dir, EXTRACTION_DIR)}/**/*.json", recursive=True):
        with open(file) as f:
            data.append(json.load(f))

    print(f"Total {len(data)} files loaded")

    parsed = []

    for e in data:
        for k, v in e['logs'].items():
            for s in v['snippets']:
                parsed.append({
                    'answers': {
                        'text': v['content'][s['start_index']-2:s['end_index']],
                        'answer_start': s['start_index']-2
                    },
                    'context': v['content'],
                    'user_comment': s['user_comment'],
                    'question': "Which part of the log is interesting?"
                })

    with open(os.path.join(tmp_dir, 'q_a_extract.json'), 'w') as f:
        json.dump(parsed, f)

    dataset = load_dataset('json', data_files=os.path.join(tmp_dir, 'q_a_extract.json'))

    if "HF_TOKEN" not in os.environ:
        raise RuntimeError("Please set HF_TOKEN so you can upload the data set to HF.")

    dataset.push_to_hub('fedora-copr/logdetective-extraction-wip',
                        token=os.getenv('HF_TOKEN'))
finally:
    shutil.rmtree(tmp_dir)
