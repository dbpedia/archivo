from archivo.datastructs.OntoloyCandidate import OntologyCandidate
from archivo.utils.requestUtils import check_robot_allowed
from archivo.validation.Step import Step
from archivo.validation.reports import ExecutionReport, Severity
from archivo.utils import archivoConfig
from archivo.logging import discovery_logger


def __robots_validation_func(oc: OntologyCandidate) -> ExecutionReport:
    # if nir not set, use initial_uri
    if not hasattr(oc, "nir"):
        uri = oc.initial_uri
    else:
        uri = oc.nir

    allowed, msg = check_robot_allowed(uri)

    if allowed:
        return ExecutionReport(Severity.OK, msg)
    else:
        return ExecutionReport(Severity.ERROR, msg)

def __check_uri_validity(oc: OntologyCandidate) -> ExecutionReport:



ROBOTS_CHECK = Step(
    label="Robots Permission Check",
    is_required=True,
    validation_func=__robots_validation_func,
    logger=discovery_logger
)

VALID_URI = Step(
    label="Initial URI Validity Check",
    is_required=True,

)
