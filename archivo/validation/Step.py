from typing import Callable, Optional
import logging
import os
import rdflib
from pyshacl import validate

from archivo.utils.graphUtils import check_highest_severity_of_graph
from archivo.datastructs.OntoloyCandidate import OntologyCandidate
from archivo.validation.reports import ExecutionReport, Severity, StepReport


class Step:
    label: str
    is_required: bool
    validation_func: Callable[[OntologyCandidate], ExecutionReport]
    log: logging.Logger

    def __init__(self,
                 label: str,
                 is_required: bool,
                 validation_func: Callable[[OntologyCandidate], ExecutionReport],
                 logger: logging.Logger,
                 in_log: bool = True):

        self.label = label
        self.is_required = is_required
        self.validation_func = validation_func
        self.in_log = in_log
        self.log = logger

    def run(self, ont_candidate: OntologyCandidate) -> StepReport:

        try:
            report = StepReport(self.label, self.validation_func(ont_candidate))
        except Exception as e:
            report = StepReport(self.label, ExecutionReport(Severity.ERROR, str(e)))

        return report


class ShaclCheck(Step):

    def __init__(self, label: str, is_required: bool, shacl_file_name: str, logger: logging.Logger):

        self.shacl_graph = loadShaclGraph(shacl_file_name)

        super().__init__(label, is_required, self.__run_shacl_check, logger)

    def __run_shacl_check(self, ont_candidate: OntologyCandidate) -> ExecutionReport:

        success, report_graph, report_text = validate(ont_candidate.graph,
                                                      shacl_graph=self.shacl_graph,
                                                      ont_graph=None,
                                                      inference="none",
                                                      abort_on_error=False,
                                                      meta_shacl=False,
                                                      debug=False,
                                                      advanced=True)

        if success:
            return ExecutionReport(Severity.OK, "No problems detected")
        else:
            # here a hacky check if its violations or Warnings
            sev = check_highest_severity_of_graph(report_graph)
            return ExecutionReport(sev, report_text)


def loadShaclGraph(filename, pub_id=None) -> rdflib.Graph:
    shacl_graph = rdflib.Graph()

    file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "shacl", filename + ".ttl"))
    with open(file_path, "r") as shaclFile:
        shacl_graph.parse(shaclFile, format="turtle", publicID=pub_id)
    return shacl_graph
