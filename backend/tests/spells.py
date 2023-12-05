"""Lyney would approve this :magic:"""

import responses


def mock_multiple_responses(url, logs):
    for name, content in logs.items():
        responses.add(responses.GET, f"{url}/{name}", body=content, status=200)


def sort_by_name(item):
    return item["name"]
