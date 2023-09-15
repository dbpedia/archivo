import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List


class LogLevel(Enum):
    """This enum consists of the four log levels: DEBUG, INFO, WARNING, ERROR. Ordered asceding."""

    DEBUG = 1
    INFO = 2
    WARNING = 3
    ERROR = 4


@dataclass
class ProcessStepLog:

    status: LogLevel
    stepname: str
    message: str

    def to_dict(self) -> dict[str, str]:

        return {
            "status": str(self.status),
            "stepname": self.stepname,
            "message": self.message,
        }


def check_is_nir_based_on_log(process_log: List[ProcessStepLog]) -> bool:

    for step_log in process_log:
        if (
            step_log.stepname
            == "Determine non-information resource (ID of the ontology)"
            and step_log.status == LogLevel.INFO
        ):
            return True

    return False
