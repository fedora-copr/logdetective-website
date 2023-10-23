import json
import random
from datetime import datetime
from pathlib import Path

from backend.constants import ProvidersEnum, FEEDBACK_DIR
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
        random_result_dir = random.choice([d for d in cls.store_to.iterdir() if d.is_dir()])
        return random.choice([f for f in random_result_dir.iterdir() if f.is_file()])
