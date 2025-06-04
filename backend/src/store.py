import os
import json
import random
from datetime import datetime
from pathlib import Path
from itertools import chain
import uuid

from src.constants import FEEDBACK_DIR, ProvidersEnum
from src.exceptions import NoDataFound
from src.schema import FeedbackSchema


class Storator3000:
    def __init__(self, provider: ProvidersEnum, id_: str) -> None:
        self.provider = provider
        self.id_ = id_
        self.store_to = Path(FEEDBACK_DIR) / str(datetime.now().date())

    @property
    def target_dir(self) -> Path:
        return self.store_to / self.provider

    @property
    def build_dir(self) -> Path:
        max_filename_length = os.pathconf("/", "PC_NAME_MAX")

        # When log is submitted from a long URL (but theoretically from other
        # source as well), the ID can be longer than 255 characters, which
        # would be over the limit for Linux filenames. In such case, let's
        # shorten it. We will lose the original URL be we won't fail.
        id_ = self.id_
        if len(self.id_) >= max_filename_length:
            id_ = self.id_[:7]

        return self.target_dir / id_

    def store(self, feedback_result: FeedbackSchema) -> uuid.UUID:
        self.build_dir.mkdir(parents=True, exist_ok=True)

        contribution_id = uuid.uuid4()
        file_name = f"{self.build_dir}/{contribution_id}.json"
        with open(file_name, "w") as fp:
            json.dump(feedback_result.dict(exclude_unset=True), fp, indent=4)
        return contribution_id

    @classmethod
    def get_logs(cls) -> list:
        if not os.path.exists(FEEDBACK_DIR):
            raise NoDataFound(f"No directory {FEEDBACK_DIR} found to get results.")

        all_files = [
            [os.path.join(subdir[0], file) for file in subdir[2]]
            for subdir in os.walk(FEEDBACK_DIR)
        ]
        # MyPy has an issue with this usage of chain.
        all_files = list(chain.from_iterable(all_files))  # type: ignore

        all_files = [x for x in all_files if x.endswith(".json")]  # type: ignore

        if not all_files:
            raise NoDataFound(f"Results directory {FEEDBACK_DIR} is empty")
        return all_files

    @classmethod
    def get_random(cls) -> Path:
        # TODO: instead of random, we should go from oldest to newest?
        #  and deprioritize those with reviews
        files = cls.get_logs()

        return Path(random.choice(files))

    @classmethod
    def get_by_id(cls, result_id: str) -> Path | None:
        """
        Return a result based on its ID
        """
        files = cls.get_logs()
        for path in files:
            if os.path.basename(path).split(".")[0] == result_id:
                return Path(path)
        return None

    @classmethod
    def get_stats(cls) -> dict:
        """Retrieve basic statistics about submitted reports."""
        files = cls.get_logs()
        stats = {
            "total_reports": len(files),
        }
        return stats
