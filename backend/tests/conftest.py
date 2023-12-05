import json
from pathlib import Path

import pytest

from src.constants import ProvidersEnum
from src.schema import FeedbackInputSchema, FeedbackSchema
from src.store import Storator3000


FAKE_BUILD_LOG = """
Mock Version: 5.5
...
"""

FAKE_BACKEND_LOG = """
[2024-02-22 13:52:52,272][  INFO][PID:1055823] Marking build as starting
[2024-02-22 13:52:52,329][  INFO][PID:1055823] Trying to allocate VM
[2024-02-22 13:52:55,354][  INFO][PID:1055823] Allocated host ResallocHost, ticket_id=424242
[2024-02-22 13:52:55,354][  INFO][PID:1055823] Allocating ssh connection to builder
...
"""

FAKE_BUILDER_LIVE_LOG = """
Warning: Permanently added '2620:52:3:1:dead:beef:cafe:c196' (ED25519) to the list of known hosts.

You can reproduce this build on your computer by running:

  sudo dnf install copr-rpmbuild
...
"""

PARENT_DIR_PATH = Path(__file__).parent


# task_id: 114607543
@pytest.fixture
def srpm_task_dict():
    with open(PARENT_DIR_PATH / "unit/test_data/task/srpm_task_dict.json") as f:
        yield json.load(f)


# task_id: 114656851
@pytest.fixture
def rpm_build_noarch_task_dict():
    with open(PARENT_DIR_PATH / "unit/test_data/task/rpm_build_noarch_task_dict.json") as f:
        yield json.load(f)


# task_id: 114657791
@pytest.fixture
def rpm_build_arch_task_dict():
    with open(PARENT_DIR_PATH / "unit/test_data/task/rpm_build_arch_task_dict.json") as f:
        yield json.load(f)


@pytest.fixture
def copr_build_dict():
    with open(PARENT_DIR_PATH / "unit/test_data/build/copr_build.json") as f:
        yield json.load(f)


@pytest.fixture
def copr_task_descendants():
    with open(PARENT_DIR_PATH / "unit/test_data/build/task_descendants.json") as f:
        yield json.load(f)


@pytest.fixture()
def fake_spec_file():
    with open(PARENT_DIR_PATH / "unit/test_data/fake.spec") as f:
        yield f.read()


@pytest.fixture()
def copr_chroot_logs():
    yield {
        "build.log.gz": FAKE_BUILD_LOG,
        "backend.log.gz": FAKE_BACKEND_LOG,
        "builder-live.log.gz": FAKE_BUILDER_LIVE_LOG,
    }


@pytest.fixture()
def copr_srpm_logs():
    yield {
        "backend.log.gz": FAKE_BACKEND_LOG,
        "builder-live.log.gz": FAKE_BUILDER_LIVE_LOG,
    }


@pytest.fixture()
def koji_chroot_logs_x86_64():
    prefix = "./backend/tests/files/koji"
    with (
        open(f"{prefix}/build_x86_64.log") as f_build_log,
        open(f"{prefix}/mock_output_x86_64.log") as f_mock_output_log,
        open(f"{prefix}/root_x86_64.log") as f_root_log,
    ):
        yield {
            "build.log": f_build_log.read(),
            "mock_output.log": f_mock_output_log.read(),
            "root.log": f_root_log.read(),
        }


@pytest.fixture
def storator():
    return Storator3000(ProvidersEnum.copr, 123)


@pytest.fixture
def spec_feedback_input_output_schema_tuple():
    yield FeedbackInputSchema(
        username="john_doe",
        logs=[
            {
                "name": "log1",
                "content": "log content 1",
                "snippets": [
                    {"start_index": 1, "end_index": 2, "user_comment": "comment1"}
                ],
            },
        ],
        fail_reason="Some reason",
        how_to_fix="Some instructions",
        spec_file={"name": "spec", "content": "spec content"},
    ), FeedbackSchema(
        username="john_doe",
        logs={
            "log1": {
                "name": "log1",
                "content": "log content 1",
                "snippets": [
                    {"start_index": 1, "end_index": 2, "user_comment": "comment1"}
                ],
            }
        },
        fail_reason="Some reason",
        how_to_fix="Some instructions",
        spec_file={"name": "spec", "content": "spec content"},
    )


@pytest.fixture
def container_feedback_input_output_schema_tuple():
    yield FeedbackInputSchema(
        username="john_doe",
        logs=[
            {
                "name": "log1",
                "content": "log content 1",
                "snippets": [
                    {"start_index": 1, "end_index": 2, "user_comment": "comment1"}
                ],
            },
        ],
        fail_reason="Some reason",
        how_to_fix="Some instructions",
        container_file={
            "name": "container_file",
            "content": "container_file content",
        },
    ), FeedbackSchema(
        username="john_doe",
        logs={
            "log1": {
                "name": "log1",
                "content": "log content 1",
                "snippets": [
                    {"start_index": 1, "end_index": 2, "user_comment": "comment1"}
                ],
            }
        },
        fail_reason="Some reason",
        how_to_fix="Some instructions",
        container_file={
            "name": "container_file",
            "content": "container_file content",
        },
    )
