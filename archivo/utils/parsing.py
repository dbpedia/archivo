import re
import subprocess
from typing import Tuple, List, Optional
from dataclasses import dataclass

from archivo.models.ContentNegotiation import RDF_Type, get_rapper_name

rapperErrorsRegex = re.compile(r"^rapper: Error.*$")
rapperWarningsRegex = re.compile(r"^rapper: Warning.*$")
rapperTriplesRegex = re.compile(r"rapper: Parsing returned (\d+) triples")

profileCheckerRegex = re.compile(r"(OWL2_DL|OWL2_QL|OWL2_EL|OWL2_RL|OWL2_FULL): OK")
pelletInfoProfileRegex = re.compile(r"OWL Profile = (.*)\n")


@dataclass
class RapperParsingResult:

    parsed_rdf: str
    rdf_type: RDF_Type
    triple_number: int
    warnings: List[str]
    errors: List[str]


def parse_rapper_errors(rapper_log: str) -> Tuple[List[str], List[str]]:
    error_matches = []
    warning_matches = []
    for line in rapper_log.split("\n"):
        if rapperErrorsRegex.match(line):
            error_matches.append(line)
        elif rapperWarningsRegex.match(line):
            warning_matches.append(line)
    return error_matches, warning_matches


def triple_number_from_rapper_log(rapper_log: str) -> int:
    match = rapperTriplesRegex.search(rapper_log)
    if match is not None:
        return int(match.group(1))
    else:
        return 0


def parse_rdf_from_string(
        rdf_string: str, base_uri: str, input_type: RDF_Type = None, output_type: RDF_Type = RDF_Type.N_TRIPLES
) -> RapperParsingResult:
    """Parses RDF content in string with Raptor RDF"""

    if input_type is None:
        command = ["rapper", "-I", base_uri, "-g", "-", "-o", get_rapper_name(output_type)]
    else:
        command = ["rapper", "-I", base_uri, "-i", get_rapper_name(input_type), "-", "-o", get_rapper_name(output_type)]

    process = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        input=bytes(rdf_string, "utf-8"),
    )
    triples = triple_number_from_rapper_log(process.stderr.decode("utf-8"))
    errors, warnings = parse_rapper_errors(process.stderr.decode("utf-8"))
    return RapperParsingResult(
        process.stdout.decode("utf-8"),
        output_type,
        triples,
        warnings,
        errors
    )


def get_triples_from_rdf_string(rdf_string: str, base_uri: str, input_type: RDF_Type = None) -> Tuple[int, List[str]]:
    if input_type is None:
        command = ["rapper", "-I", base_uri, "-g", "-"]
    else:
        command = ["rapper", "-I", base_uri, "-i", get_rapper_name(input_type), "-"]

    process = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        input=bytes(rdf_string, "utf-8"),
    )
    triples = triple_number_from_rapper_log(process.stderr.decode("utf-8"))
    errors, _ = parse_rapper_errors(process.stderr.decode("utf-8"))
    return triples, errors