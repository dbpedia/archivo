import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict


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
