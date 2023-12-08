import os
import json
import random
from datetime import datetime
from pathlib import Path

from backend.constants import FEEDBACK_DIR, ProvidersEnum
from backend.exceptions import NoDataFound
from backend.schema import FeedbackSchema
from itertools import chain


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

    def store(self, feedback_result: FeedbackSchema) -> None:
        self.build_dir.mkdir(parents=True, exist_ok=True)

        timestamp_seconds = int(datetime.now().timestamp())
        file_name = self.build_dir / f"{timestamp_seconds}.json"
        with open(file_name, "w") as fp:
            json.dump(feedback_result.dict(exclude_unset=True), fp, indent=4)

    @classmethod
    def get_random(cls) -> Path:
        # TODO: instead of random, we should go from oldest to newest?
        #  and deprioritize those with reviews
        if not os.path.exists(FEEDBACK_DIR):
            raise NoDataFound(f"Directory doesn't exist: {FEEDBACK_DIR}")

        all_files = [[
                        os.path.join(subdir[0], file)
                        for file in subdir[2]
                    ]
                for subdir in os.walk(FEEDBACK_DIR)]

        return Path(random.choice(list(chain.from_iterable(all_files))))
