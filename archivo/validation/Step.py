from typing import Callable, Optional, Dict, Tuple
import logging
import os
import rdflib
from pyshacl import validate

from archivo.utils import archivoConfig
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


class FileCreationStep(Step):

    def __init__(self,
                 label: str,
                 is_required: bool,
                 content_variants: Dict[str, str],
                 filetype: str,
                 creation_func: Callable[[OntologyCandidate], Tuple[str, ExecutionReport]],
                 logger: logging.Logger):

        self.content_variants = content_variants
        self.filetype = filetype
        self.creation_func = creation_func

        super().__init__(label, is_required, self.__create_files, logger)

    @staticmethod
    def __create_necessary_directories(path: str) -> None:
        os.makedirs(path, exist_ok=True)

    def __create_files(self, ont_candidate: OntologyCandidate) -> ExecutionReport:

        try:
            groupid, artifactid = ont_candidate.get_group_and_artifact()

            versionID = ont_candidate.getVersionID()

            directory = os.path.join(archivoConfig.localPath, groupid, artifactid, versionID)
            FileCreationStep.__create_necessary_directories(directory)

            cv_part = "_".join([f"{k}={v}" for k, v in self.content_variants])
            filename = f"{artifactid}_{cv_part}.{self.filetype}"

            content, report = self.creation_func(ont_candidate)

            filepath = os.path.join(directory, filename)
            with open(filepath, "w+") as output_file:
                output_file.write(content)
            return report
        except Exception as e:
            return ExecutionReport(Severity.ERROR, str(e))


class ShaclCheck(FileCreationStep):

    def __init__(self, label: str, is_required: bool, shacl_file_name: str, content_variants: Dict[str, str], logger: logging.Logger):

        self.shacl_graph = ShaclCheck.load_shacl_graph(shacl_file_name)

        def run_shacl_check(ont_candidate: OntologyCandidate) -> Tuple[str, ExecutionReport]:

            success, report_graph, report_text = validate(ont_candidate.graph,
                                                          shacl_graph=self.shacl_graph,
                                                          ont_graph=None,
                                                          inference="none",
                                                          abort_on_error=False,
                                                          meta_shacl=False,
                                                          debug=False,
                                                          advanced=True)

            if success:
                return report_graph.serialize(format="turtle"), ExecutionReport(Severity.OK, "No problems detected")
            else:
                # here a hacky check if its violations or Warnings
                sev = check_highest_severity_of_graph(report_graph)
                return report_graph.serialize(format="turtle"), ExecutionReport(sev, report_text)

        super().__init__(label=label,
                         is_required=is_required,
                         content_variants=content_variants,
                         filetype="ttl",
                         creation_func=run_shacl_check,
                         logger=logger)

    @staticmethod
    def load_shacl_graph(filename, pub_id=None) -> rdflib.Graph:
        shacl_graph = rdflib.Graph()

        file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "shacl", filename + ".ttl"))
        with open(file_path, "r") as shaclFile:
            shacl_graph.parse(shaclFile, format="turtle", publicID=pub_id)
        return shacl_graph
