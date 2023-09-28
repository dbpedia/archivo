from dataclasses import dataclass
from logging import Logger
from typing import Tuple, List, Set, Optional, Dict

from crawling.discovery import ArchivoVersion
from models import content_negotiation
from models.content_negotiation import RDF_Type
from models.crawling_response import CrawlingResponse
from models.data_writer import DataWriter
import requests
from crawling import discovery
from datetime import datetime
import os
import json
import re

from models.user_interaction import ProcessStepLog
from utils import (
    string_tools,
    archivo_config,
    async_rdf_retrieval,
    parsing,
    content_access,
)
from querying import graph_handling
from utils.archivo_exceptions import (
    UnavailableContentException,
    UnparseableRDFException,
)
from utils.archivoLogs import diff_logger
from models.databus_identifier import (
    DatabusVersionIdentifier,
    DatabusFileMetadata,
)
from utils.validation import TestSuite
from utils.parsing import RapperParsingResult

__SEMANTIC_VERSION_REGEX = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

__ENVIRONMENT = os.environ.copy()
__ENVIRONMENT["LC_ALL"] = "C"


@dataclass
class DiffResult:
    is_diff: bool
    old_content: str
    new_content: str
    old_triples: Set[str]
    new_triples: Set[str]


def no_ignored_props_in_line(line: str):
    for prop in archivo_config.DIFF_IGNORE_PROPERTIES:
        if prop in line:
            return False
    return True


def diff_content(old_triples: List[str], new_triples: List[str], logger: Logger = diff_logger) -> DiffResult:
    """Checks the diff with python builtins. Also handles deduplication and empty lines. Returns a DiffResult"""

    def filterfun(x: str):
        """Kicking out empty lines"""
        return x.strip() != ""

    old_set_filtered = set(filter(filterfun, set(old_triples)))
    new_set_filtered = set(filter(filterfun, set(new_triples)))

    new_triples = new_set_filtered - old_set_filtered
    old_triples = old_set_filtered - new_set_filtered

    is_diff = bool(set(filter(no_ignored_props_in_line, old_triples))) or bool(
        set(filter(no_ignored_props_in_line, new_triples))
    )

    return DiffResult(
        is_diff,
        "\n".join(old_triples),
        "\n".join(new_triples),
        old_triples,
        new_triples,
    )


def check_for_new_version(
    vocab_uri: str,
    old_e_tag: str,
    old_last_mod: str,
    old_content_length: str,
    best_header: str,
) -> bool:
    """Check the location of the vocab with a HEAD request and check if new content is available.
    Returns true if new version is available, else false."""

    if (
        string_tools.is_none_or_empty(old_e_tag)
        and string_tools.is_none_or_empty(old_last_mod)
        and string_tools.is_none_or_empty(old_content_length)
    ):
        # if none of the old versions are compareable -> full download diff is always needed
        return True

    response = requests.head(
        vocab_uri, headers={"Accept": best_header}, timeout=30, allow_redirects=True
    )

    if response.status_code > 400:
        raise UnavailableContentException(response)

    new_e_tag = string_tools.getEtagFromResponse(response)
    new_last_mod = string_tools.getLastModifiedFromResponse(response)
    new_content_length = string_tools.getContentLengthFromResponse(response)
    if (
        old_e_tag == new_e_tag
        and old_last_mod == new_last_mod
        and old_content_length == new_content_length
    ):
        return False
    else:
        return True


def handle_slash_uris(
    uri: str, header: str, response: requests.Response, logger: Logger
) -> RapperParsingResult:

    # parse it as turtle because rdflib used to have problems with parsing from ntriples
    turtle_parsing_result = parsing.parse_rdf_from_string(
        response.text,
        uri,
        input_type=content_negotiation.get_rdf_type(header),
        output_type=content_negotiation.RDF_Type.TURTLE,
    )

    if turtle_parsing_result.parsing_info.errors:
        raise UnparseableRDFException(
            f"Found {len(turtle_parsing_result.parsing_info.errors)} Errors during parsing:\n"
            + "\n".join(turtle_parsing_result.parsing_info.errors)
        )

    graph = graph_handling.get_graph_of_string(
        turtle_parsing_result.parsed_rdf, RDF_Type.TURTLE
    )

    crawl_parsing_results, retrieval_errors = async_rdf_retrieval.gather_linked_content(
        uri,
        graph,
        pref_header=header,
        concurrent_requests=50,
        logger=logger,
    )

    error_str = "Failed retrieval for content:\n" + "\n".join(
        [" -- ".join(tp) for tp in retrieval_errors]
    )

    if retrieval_errors:
        logger.warning(error_str)

    if len(crawl_parsing_results) <= 0:
        return RapperParsingResult(
            response.text,
            content_negotiation.get_rdf_type(header),
            turtle_parsing_result.parsing_info,
        )

    async_rdf_retrieval.join_ntriples_results(crawl_parsing_results)

    nt_parsing_result = parsing.parse_rdf_from_string(
        response.text,
        uri,
        input_type=content_negotiation.get_rdf_type(header),
        output_type=content_negotiation.RDF_Type.N_TRIPLES,
    )

    # append original nt content to retrieved content
    crawl_parsing_results.append(nt_parsing_result)

    return async_rdf_retrieval.join_ntriples_results(crawl_parsing_results)


def diff_check_new_file(
    uri: str,
    old_metadata: Dict,
    old_version_id: DatabusVersionIdentifier,
    dev_uri: Optional[str],
    logger: Logger,
) -> Tuple[
    Optional[DiffResult], Optional[CrawlingResponse], Optional[RapperParsingResult]
]:
    if dev_uri is None:
        locURI = uri
    else:
        locURI = dev_uri

    oldETag = old_metadata["http-data"]["e-tag"]
    oldLastMod = old_metadata["http-data"]["lastModified"]
    bestHeader = old_metadata["http-data"]["best-header"]
    contentLength = old_metadata["http-data"]["content-length"]

    has_new_version = check_for_new_version(
        locURI, oldETag, oldLastMod, contentLength, bestHeader
    )

    if not has_new_version:
        # if there are no possible further values, we are done
        return None, None, None

    output: List[ProcessStepLog] = []

    crawling_response = discovery.determine_best_content_type(
        locURI, user_output=output
    )
    crawling_response.response.encoding = "utf-8"

    if crawling_response is None:
        error_str = f"Error in step {output[-1].stepname}: {output[-1].message}"
        raise UnavailableContentException(error_str)

    parsing_result = parsing.parse_rdf_from_string(
        crawling_response.response.text,
        uri,
        input_type=crawling_response.rdf_type,
        output_type=content_negotiation.RDF_Type.N_TRIPLES,
    )

    # raising an exception if there are no triples in the result
    if parsing_result.parsing_info.triple_number <= 0:
        raise UnparseableRDFException("\n".join(parsing_result.parsing_info.errors))

    old_nt_file_metadata = DatabusFileMetadata(
        old_version_id,
        sha_256_sum="",
        content_length=-1,
        content_variants={"type": "parsed"},
        file_extension="nt",
        compression=None,
    )

    old_file_nt_content = content_access.get_databus_file(old_nt_file_metadata)
    old_content_triples = old_file_nt_content.split("\n")
    new_content_triples = parsing_result.parsed_rdf.split("\n")

    diff_result = diff_content(old_content_triples, new_content_triples)

    return diff_result, crawling_response, parsing_result


def create_diff_files(
    data_writer: DataWriter,
    diff_result: DiffResult,
    databus_version_id: DatabusVersionIdentifier,
    old_axioms: Set[str],
    new_axioms: Set[str],
) -> None:

    # create diff triples

    for triples_type, content in [
        ("new", diff_result.new_content),
        ("old", diff_result.old_content),
    ]:

        shasum, content_length = string_tools.get_content_stats(bytes(content, "utf-8"))
        db_file_metadata = DatabusFileMetadata(
            version_identifier=databus_version_id,
            content_length=content_length,
            sha_256_sum=shasum,
            compression=None,
            content_variants={"type": "diff", "triples": triples_type},
            file_extension="nt",
        )

        data_writer.write_databus_file(
            db_file_metadata=db_file_metadata, content=content
        )

    for axiom_type, content in [("new", new_axioms), ("old", old_axioms)]:
        content = "\n".join(content)
        shasum, content_length = string_tools.get_content_stats(
            bytes("\n".join(content), "utf-8")
        )
        db_file_metadata = DatabusFileMetadata(
            version_identifier=databus_version_id,
            content_length=content_length,
            sha_256_sum=shasum,
            compression=None,
            content_variants={"type": "diff", "axioms": axiom_type},
            file_extension="dl",
        )

        data_writer.write_databus_file(
            content=content, db_file_metadata=db_file_metadata
        )


def update_for_ontology_uri(
    uri: str,
    source: str,
    last_version_timestamp: str,
    data_writer: DataWriter,
    test_suite: TestSuite,
    dev_uri: Optional[str] = None,
    logger: Logger = diff_logger,
) -> Tuple[bool, str, Optional[ArchivoVersion]]:
    try:
        metadata, old_version_id = prepare_diff_for_ontology(
            uri=uri,
            last_version_timestamp=last_version_timestamp,
            dev_uri=dev_uri,
        )
        diff_result, crawling_response, parsing_result = diff_check_new_file(
            uri=uri,
            dev_uri=dev_uri,
            logger=logger,
            old_metadata=metadata,
            old_version_id=old_version_id,
        )
    except Exception as e:
        logger.warning(str(e))
        return False, str(e), None

    if not diff_result or not diff_result.is_diff:
        if diff_result:
            logger.info(f"No difference in the triples, no new version")
        else:
            logger.info(f"No difference in the header files, no crawling happening")
        return False, f"No different version for {uri}", None
    # New version!

    logger.info(
        f"New, different version for ontology {uri}: {len(diff_result.old_triples)} old triples, {len(diff_result.new_triples)} new triples"
    )

    new_version_identifier = DatabusVersionIdentifier(
        archivo_config.DATABUS_USER,
        old_version_id.group,
        old_version_id.artifact,
        datetime.now().strftime("%Y.%m.%d-%H%M%S"),
    )

    old_ont_axioms = test_suite.get_axioms_of_rdf_ontology(diff_result.old_content)
    new_ont_axioms = test_suite.get_axioms_of_rdf_ontology(diff_result.new_content)

    old_sem_version = metadata["ontology-info"]["semantic-version"]

    new_sem_version, old_diff_axioms, new_diff_axioms = build_new_semantic_version(
        old_sem_version, old_ont_axioms, new_ont_axioms, logger=logger
    )

    create_diff_files(
        data_writer,
        diff_result,
        new_version_identifier,
        old_diff_axioms,
        new_diff_axioms,
    )

    new_version = ArchivoVersion(
        confirmed_ontology_id=uri,
        crawling_result=crawling_response,
        parsing_result=parsing_result,
        databus_version_identifier=new_version_identifier,
        test_suite=test_suite,
        access_date=datetime.now(),
        source=source,
        data_writer=data_writer,
        logger=logger,
    )

    logger.info("Deploying the data to the databus...")

    new_version.generate_files()
    return True, "Updated ontology", new_version
    # try:
    #     new_version.deploy(True)
    #     logger.info(f"Successfully deployed the new update of ontology {uri}")
    #     return (
    #         True,
    #         f"Successfully deployed the new update of ontology {uri}",
    #         new_version,
    #     )
    # except Exception as e:
    #     logger.error("There was an Error deploying to the databus")
    #     logger.error(str(e))
    #     return False, "ERROR: Couldn't deploy to databus!", new_version


def prepare_diff_for_ontology(
    uri: str,
    last_version_timestamp: str,
    dev_uri: Optional[str] = None,
) -> Tuple[Dict, DatabusVersionIdentifier]:
    """Prepares the local structure for the diff"""

    groupId, artifact = string_tools.generate_databus_identifier_from_uri(
        uri, dev=bool(dev_uri)
    )

    old_db_verison_id = DatabusVersionIdentifier(
        user="ontologies",
        group=groupId,
        artifact=artifact,
        version=last_version_timestamp,
    )

    old_metadata_file_metadata = DatabusFileMetadata(
        old_db_verison_id,
        sha_256_sum="",
        content_length=-1,
        content_variants={"type": "meta"},
        file_extension="json",
        compression=None,
    )

    metadata = json.loads(content_access.get_databus_file(old_metadata_file_metadata))

    return metadata, old_db_verison_id


def build_new_semantic_version(
    old_semantic_version: str,
    old_axiom_set: Set[str],
    new_axiom_set: Set[str],
    logger=diff_logger,
) -> Tuple[str, Set[str], Set[str]]:
    old = old_axiom_set - new_axiom_set
    new = new_axiom_set - old_axiom_set

    logger.info("Old Axioms:\n" + "\n".join(old))
    logger.info("New Axioms:\n" + "\n".join(new))

    match = __SEMANTIC_VERSION_REGEX.match(old_semantic_version)
    if match is None:
        logger.warning(f"Bad format of semantic version: {old_semantic_version}")
        return (
            "ERROR: Can't build new semantic version because last is broken",
            old,
            new,
        )

    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3))

    if old == set() and new == set():
        return f"{str(major)}.{str(minor)}.{str(patch + 1)}", old, new
    elif new != set() and old == set():
        return f"{str(major)}.{str(minor + 1)}.{str(0)}", old, new
    else:
        return f"{str(major + 1)}.{str(0)}.{str(0)}", old, new
