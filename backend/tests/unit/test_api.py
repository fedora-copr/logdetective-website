"""
Test the API endpoints.
"""

import os

from src.api import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_our_server_url(tmp_path):
    """
    Test that the server URL is properly set in the response.
    """
    os.environ["FEEDBACK_DIR"] = str(tmp_path / "results")
    data = {
        "username": "FAS:me",
        "fail_reason": "Failed because...",
        "how_to_fix": "Like this...",
        "spec_file": {
            "name": "llvm.spec",
            "content": "Yes, the actual content of the spec file",
        },
        "logs": [
            {
                "name": "build.log",
                "content": "content of the build log",
                "snippets": [
                    {
                        "start_index": 1,
                        "end_index": 2,
                        "user_comment": "this snippet is relevant because...",
                        "text": "content of the snippet",
                    }
                ],
            }
        ],
    }
    response = client.post("/frontend/contribute/copr/1/x86_64", json=data)
    assert response.status_code == 200
    response_json = response.json()
    assert response_json["review_url_json"].startswith(
        f"{client.base_url}/frontend/review/"
    )
    assert response_json["review_url_website"].startswith(f"{client.base_url}/review/")
