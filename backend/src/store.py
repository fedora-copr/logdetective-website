import os
import json
import random
from datetime import datetime
from pathlib import Path
from itertools import chain

from src.constants import FEEDBACK_DIR, ProvidersEnum
from src.exceptions import NoDataFound
from src.schema import FeedbackSchema


class Storator3000:
    def __init__(self, provider: ProvidersEnum, id_: int | str) -> None:
        self.provider = provider
        self.id_ = id_
        self.store_to = Path(FEEDBACK_DIR) / str(datetime.now().date())

    @property
    def target_dir(self) -> Path:
        return self.store_to / self.provider

    @property
    def build_dir(self) -> Path:
        return self.target_dir / str(self.id_)

    def store(self, feedback_result: FeedbackSchema) -> None:
        self.build_dir.mkdir(parents=True, exist_ok=True)

        timestamp_seconds = int(datetime.now().timestamp())
        file_name = self.build_dir / f"{timestamp_seconds}.json"
        with open(file_name, "w") as fp:
            json.dump(feedback_result.dict(exclude_unset=True), fp, indent=4)

    @classmethod
    def get_logs(cls) -> list:
        if not os.path.exists(FEEDBACK_DIR):
            return []

        all_files = [[
                        os.path.join(subdir[0], file)
                        for file in subdir[2]
                    ]
                for subdir in os.walk(FEEDBACK_DIR)]
        # MyPy has an issue with this usage of chain.
        all_files = list(chain.from_iterable(all_files))  # type: ignore

        if not all_files:
            raise NoDataFound(f"Results directory {FEEDBACK_DIR} is empty")
        return all_files

    @classmethod
    def get_latest(cls) -> Path:
        """Sort stored logs by timestamp and return the newest.
        """
        files = cls.get_logs()
        files = sorted(
            files,
            key=lambda x: x.split('/')[-1],
            reverse=True)

        return Path(files[0])

    @classmethod
    def get_random(cls) -> Path:
        # TODO: instead of random, we should go from oldest to newest?
        #  and deprioritize those with reviews
        files = cls.get_logs()

        return Path(random.choice(files))

    @classmethod
    def get_stats(cls) -> dict:
        """Retrieve basic statistics about submitted reports.
        """
        files = cls.get_logs()
        stats = {
            "total_reports" : len(files),
        }
        return stats
