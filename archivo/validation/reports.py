from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Severity(Enum):
    """Enum for different severities of results"""

    OK = 0
    INFO = 1
    WARNING = 2
    ERROR = 3


@dataclass
class ExecutionReport:
    """A class bundeling the reports"""

    check_severity: Severity
    check_message: str
    check_message_for_webpage: Optional[str] = None


@dataclass
class StepReport:
    label: str
    execution_report: ExecutionReport
