import logging
from typing import List, Iterator

from archivo.datastructs.OntoloyCandidate import OntologyCandidate
from archivo.validation.Step import Step
from archivo.validation.reports import ExecutionReport


class ValidationChain:
    label: str
    log: logging.Logger
    steps: List[Step]

    def __init__(self, label: str, logger: logging.Logger, *step: Step):
        self.label = label
        self.log = logger
        self.steps = list(step)

    def execute(self, ont_candidate: OntologyCandidate) -> Iterator[ExecutionReport]:
        for step in self.steps:
            step_report = step.validation_func(ont_candidate)

            # check if status is worse then INFO
            if int(step_report.check_severity.value()) >= 2 and step.is_required:
                self.log.error(f"Could not satisfy step {step.label}: {step_report.check_message}")
                break
            else:
                yield step.validation_func(ont_candidate)
