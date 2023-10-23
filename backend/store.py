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
        with open(file_name, "w") as json_file:
            json_output = json.dumps(feedback_result.json())
            json_file.write(json_output)

    @classmethod
    def get_random(cls) -> Path:
        # TODO: instead of random, we should go from oldest to newest?
        #  and deprioritize those with reviews
        day_dirs = [d for d in Path(FEEDBACK_DIR).iterdir() if d.is_dir()]
        if not day_dirs:
            raise NoDataFound("No data found to get random results")

        random_day_dir = random.choice(day_dirs)
        random_provider_dir = random.choice(
            [d for d in random_day_dir.iterdir() if d.is_dir()]
        )
        random_build_dir = random.choice(
            [d for d in random_provider_dir.iterdir() if d.is_dir()]
        )
        return random.choice([f for f in random_build_dir.iterdir() if f.is_file()])
