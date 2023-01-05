import validators

from archivo.datastructs.OntoloyCandidate import OntologyCandidate
from archivo.utils.requestUtils import check_robot_allowed
from archivo.utils.stringTools import get_uri_from_index
from archivo.validation.Step import Step
from archivo.validation.reports import ExecutionReport, Severity
from archivo.config import ARCHIVO_CONFIG
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
    candidate_fields = ["initial_uri", "nir", "dev_uri"]

    for candidate in candidate_fields:
        # check wether the attribute is present
        if hasattr(oc, candidate):

            url_str = getattr(oc, candidate)
            try:
                assert validators.url(url_str)
            except AssertionError:
                return ExecutionReport(Severity.ERROR, f"Malformed URI for {candidate}: {url_str}")


def __check_index(oc: OntologyCandidate) -> ExecutionReport:
    candidate_fields = ["nir", "dev_uri"]

    index = []

    for candidate in candidate_fields:
        # check wether the attribute is present
        if hasattr(oc, candidate):

            url_str = getattr(oc, candidate)

            found_index_uri = get_uri_from_index(url_str, index)

            if found_index_uri:
                return ExecutionReport(check_severity=Severity.ERROR, check_message=f"URI {url_str} already in index")
            else:
                return ExecutionReport(check_severity=Severity.OK, check_message=f"URI {url_str} is new")

    # if no candidate fields: ERROR
    return ExecutionReport(check_severity=Severity.ERROR, check_message=f"INTERNAL ERROR: NO URL GIVEN")


ROBOTS_CHECK = Step(
    label="Robots Permission Check",
    is_required=True,
    validation_func=__robots_validation_func,
    logger=discovery_logger
)

VALID_URI = Step(
    label="URI Validity Check",
    is_required=True,
    validation_func=__check_uri_validity,
    logger=discovery_logger
)

INDEX_CHECK = Step(
    label="Index Check",
    is_required=True,
    validation_func=__check_index,
    logger=discovery_logger
)
