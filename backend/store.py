import os
import json
import random
from datetime import datetime
from pathlib import Path

from backend.constants import FEEDBACK_DIR, ProvidersEnum
from backend.exceptions import NoDataFound
from backend.schema import ResultSchema


class Storator3000:
    store_to = Path(FEEDBACK_DIR) / str(datetime.now().date())

    def __init__(self, provider: ProvidersEnum, id_: int | str) -> None:
        self.provider = provider
        self.id_ = id_

    @property
    def target_dir(self) -> Path:
        return self.store_to / self.provider

    @property
    def build_dir(self) -> Path:
        return self.target_dir / str(self.id_)

    def store(self, feedback_result: ResultSchema) -> None:
        self.build_dir.mkdir(parents=True, exist_ok=True)

        timestamp_seconds = int(datetime.now().timestamp())
        file_name = self.build_dir / f"{timestamp_seconds}.json"
        with open(file_name, "w") as fp:
            json.dump(feedback_result.dict(), fp, indent=4)

    @staticmethod
    def _get_random_dir_from(dir_: Path) -> Path:
        iter_dir = [d for d in dir_.iterdir() if d.is_dir()]
        if not iter_dir:
            raise NoDataFound("No data found to get random results")

        return random.choice(iter_dir)

    @classmethod
    def get_random(cls) -> Path:
        # TODO: instead of random, we should go from oldest to newest?
        #  and deprioritize those with reviews
        if not os.path.exists(FEEDBACK_DIR):
            raise NoDataFound("Directory doesn't exist: {}".format(FEEDBACK_DIR))

        random_day_dir = cls._get_random_dir_from(Path(FEEDBACK_DIR))
        random_provider_dir = cls._get_random_dir_from(random_day_dir)
        random_build_dir = cls._get_random_dir_from(random_provider_dir)
        random_contribute = [f for f in random_build_dir.iterdir() if f.is_file()]
        if not random_contribute:
            raise NoDataFound("No contribute data found")

        return random.choice(random_contribute)
