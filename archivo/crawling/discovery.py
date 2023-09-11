from logging import Logger
from os.path import isfile
from typing import Dict, List, Optional, Tuple, Set

import hashlib

import databusclient
import rdflib
import requests
import os
import traceback
from datetime import datetime

from rdflib import Graph
from requests import Response

from archivo.crawling.archivo_version import ArchivoVersion
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse, urldefrag, quote

from archivo.models.content_negotiation import RDF_Type
from archivo.models.data_writer import DataWriter, FileWriter
from archivo.models.databus_identifier import DatabusVersionIdentifier
from archivo.models.user_interaction import ProcessStepLog, LogLevel
from archivo.utils import (
    string_tools,
    archivo_config,
    graph_handling,
    parsing,
)
from archivo.utils.validation import TestSuite

from best_effort_crawling import determine_best_content_type


def check_robot(uri: str) -> Tuple[Optional[bool], Optional[str]]:
    parsedUrl = urlparse(uri)
    if parsedUrl.scheme == "" or parsedUrl.netloc == "":
        return None, None
    robotsUrl = str(parsedUrl.scheme) + "://" + str(parsedUrl.netloc) + "/robots.txt"
    try:
        req = requests.get(url=robotsUrl)
    except Exception as e:
        return True, str(e)

    if req.status_code > 400:
        # if robots.txt is not accessible, we are allowed
        return True, None
    rp = RobotFileParser()
    rp.set_url(robotsUrl)
    rp.parse(req.text.split("\n"))
    if rp.can_fetch(archivo_config.archivo_agent, uri):
        return True, None
    else:
        return False, "Not allowed"


# returns the NIR if fragment-equivalent, else None
def check_ontology_id_uri(
    uri: str, graph: rdflib.Graph, output: List[ProcessStepLog] = None
) -> Tuple[bool, Optional[str]]:
    """Checks for the existence of an ontology ID and checks if it is equal to the input URI.
    Returns A Tuple of"""

    if output is None:
        output = []
    candidates = graph_handling.get_ontology_uris(graph)

    if not candidates:
        output.append(
            ProcessStepLog(
                status=LogLevel.ERROR,
                stepname="Determine non-information resource (ID of the ontology)",
                message="Can't neither find a triple with <code>owl:Ontology</code> or <code>skos:ConceptScheme</code> as value",
            )
        )
        return False, None

    found_nir = None

    for nir in candidates:
        if string_tools.check_uri_equality(uri, nir):
            found_nir = nir
            break

    if found_nir is None:
        output.append(
            ProcessStepLog(
                status=LogLevel.WARNING,
                stepname="Determine non-information resource (ID of the ontology)",
                message=f"Neither of {str(candidates)} equals the source URI {uri}, trying to validate {candidates[0]}",
            )
        )
        return False, candidates[0]
    else:
        output.append(
            ProcessStepLog(
                status=LogLevel.INFO,
                stepname="Determine non-information resource (ID of the ontology)",
                message=f"Found non-information resource: {found_nir}",
            )
        )
        return True, found_nir


def perform_robot_check(
    vocab_uri: str, user_output: List[ProcessStepLog], logger: Logger
) -> bool:
    allowed, message = check_robot(vocab_uri)
    logger.info(f"Robot allowed: {allowed}")
    if not allowed:
        logger.warning(f"{archivo_config.archivo_agent} not allowed")
        user_output.append(
            ProcessStepLog(
                status=LogLevel.ERROR,
                stepname="Robot allowance check",
                message=f"Archivo-Agent {archivo_config.archivo_agent} is not allowed to access the ontology at <a href={vocab_uri}>{vocab_uri}</a>",
            )
        )
        return False
    else:
        user_output.append(
            ProcessStepLog(
                status=LogLevel.INFO,
                stepname="Robot allowance check",
                message=f"Archivo-Agent {archivo_config.archivo_agent} is allowed.",
            )
        )
        return True


def parse_uri(uri: str) -> Tuple[str, str, str]:
    """Takes an URI and returns the defragmented URI, a"""

    defrag_uri = urldefrag(uri)[0]
    group_id, artifact_id = string_tools.generate_databus_identifier_from_uri(
        defrag_uri
    )

    return defrag_uri, group_id, artifact_id


def searching_for_linked_ontologies(
    uri: str,
    found_ontology_id: Optional[str],
    onto_graph: rdflib.Graph,
    vocab_uri_cache: List[str],
    logger: Logger,
    process_log: List[ProcessStepLog],
    recursion_depth: int,
) -> Optional[ArchivoVersion]:

    match found_ontology_id:
        case None:
            # This means there is no ontology ID whatsoever. Try using isDefinedBy to find its defining vocab.
            defined_by_uri = graph_handling.get_defined_by_uri(onto_graph)

            match defined_by_uri:
                case None:
                    process_log.append(
                        ProcessStepLog(
                            status=LogLevel.ERROR,
                            stepname="Searching for linked ontologies",
                            message=f"The document given at {uri} does not contain a <code>rdfs:isDefinedBy</code> or <code>skos:inScheme</code> triple",
                        )
                    )
                    return None
                case def_by_uri if not string_tools.check_uri_equality(def_by_uri, uri):
                    process_log.append(
                        ProcessStepLog(
                            status=LogLevel.INFO,
                            stepname="Searching for linked ontologies",
                            message=f"Found linked potential ontology at {def_by_uri}",
                        )
                    )
                    return discover_new_uri(
                        uri=def_by_uri,
                        vocab_uri_cache=vocab_uri_cache,
                        logger=logger,
                        process_log=process_log,
                        recursion_depth=recursion_depth + 1,
                        is_develop_version=False,
                    )
                case def_by_uri if string_tools.check_uri_equality(def_by_uri, uri):
                    process_log.append(
                        ProcessStepLog(
                            status=LogLevel.ERROR,
                            stepname="Searching for linked ontologies",
                            message=f"The document given at {uri} links to itself via an <code>rdfs:isDefinedBy</code> or <code>skos:inScheme</code> triple but is no ontology",
                        )
                    )
                    return None

        case nir:
            # This means the crawled URI and the found ontology ID are inconsistent. Try crawling the new value.
            process_log.append(
                ProcessStepLog(
                    status=LogLevel.INFO,
                    stepname="Ontology Identification",
                    message=f"The document given at {uri} links to itself via an <code>rdfs:isDefinedBy</code> or <code>skos:inScheme</code> triple, bit is no ontology",
                )
            )
            if recursion_depth <= archivo_config.max_recursion_depth:
                return discover_new_uri(
                    uri=nir,
                    vocab_uri_cache=vocab_uri_cache,
                    logger=logger,
                    process_log=process_log,
                    recursion_depth=recursion_depth + 1,
                    is_develop_version=False,
                )
            else:
                process_log.append(
                    ProcessStepLog(
                        status=LogLevel.ERROR,
                        stepname="Searching for linked ontologies",
                        message=f"Maximum recursion depth of {archivo_config.max_recursion_depth} reached",
                    )
                )
                return None


def discover_new_uri(
    uri: str,
    vocab_uri_cache: List[str],
    data_writer: DataWriter,
    test_suite: TestSuite,
    source: str,
    logger: Logger,
    process_log: List[ProcessStepLog] = None,
    recursion_depth: int = 1,
    is_develop_version: bool = False,
) -> Optional[ArchivoVersion]:

    if process_log is None:
        process_log = []

    uri, group_id, artifact_id = parse_uri(uri)

    # Check if URI was malformed
    if group_id is None or artifact_id is None:
        process_log.append(
            ProcessStepLog(
                status=LogLevel.ERROR,
                stepname="URI parsing check",
                message=f"ERROR: Malformed URI {uri}",
            )
        )
        return None

    # check if uri is in cache
    found_uri = string_tools.get_uri_from_index(uri, vocab_uri_cache)
    if found_uri is not None:
        logger.info("Already known uri, skipping...")
        process_log.append(
            ProcessStepLog(
                status=LogLevel.INFO,
                stepname="Index check",
                message=f"This Ontology is already in the Archivo index and can be found at <a href=/info?o={quote(found_uri)}>here</a>",
            )
        )
        return None

    if not perform_robot_check(uri, process_log, logger):
        return None

    crawling_result = determine_best_content_type(uri, user_output=process_log)

    if crawling_result is None:
        return None

    # now there is RDF and its parseable, we can now check if it is an ontology
    access_date = datetime.now()
    version_id = access_date.strftime("%Y.%m.%d-%H%M%S")

    # parse the content with rapper since its more consumeable by rdflib and load it into a graph

    parsing_result_turtle = parsing.parse_rdf_from_string(
        crawling_result.response.text, uri, crawling_result.rdf_type, RDF_Type.TURTLE
    )

    try:
        onto_graph = graph_handling.get_graph_of_string(
            parsing_result_turtle.parsed_rdf, RDF_Type.TURTLE
        )
    except Exception:
        logger.error(f"Exception in rdflib parsing of URI {uri}", exc_info=True)
        process_log.append(
            ProcessStepLog(
                status=LogLevel.ERROR,
                stepname="Load Graph in rdflib",
                message=f"RDFlib couldn't parse the file of {uri}. Reason: {traceback.format_exc()}",
            )
        )
        return None

    success, ontology_id_uri = check_ontology_id_uri(uri, onto_graph, process_log)

    if not success:
        # this means no ontology ID could be found
        return searching_for_linked_ontologies(
            uri=uri,
            found_ontology_id=ontology_id_uri,
            onto_graph=onto_graph,
            vocab_uri_cache=vocab_uri_cache,
            logger=logger,
            process_log=process_log,
            recursion_depth=recursion_depth,
        )

    # Now from here on it is a confirmed ontology
    process_log.append(
        ProcessStepLog(
            status=LogLevel.INFO,
            stepname="Determine non-information resource (ID of the ontology)",
            message=f"Successfully identified Ontology from {uri} with ID {ontology_id_uri}",
        )
    )

    # overwrite generated databus identifiers
    group_id, artifact_id = string_tools.generate_databus_identifier_from_uri(
        ontology_id_uri
    )

    # again malformed check
    if group_id is None or artifact_id is None:
        process_log.append(
            ProcessStepLog(
                status=LogLevel.ERROR,
                stepname="URI parsing check",
                message=f"ERROR: Malformed ontology ID in document: {ontology_id_uri}",
            )
        )
        return None

    # again cache check
    found_uri = string_tools.get_uri_from_index(ontology_id_uri, vocab_uri_cache)
    if found_uri is not None:
        logger.info("Already known uri, skipping...")
        process_log.append(
            ProcessStepLog(
                status=LogLevel.INFO,
                stepname="Index check",
                message=f"This Ontology is already in the Archivo index and can be found at <a href=/info?o={quote(found_uri)}>here</a>",
            )
        )
        return None

    group_info = {
        "title": f"DBpedia Archivo ontologies from the {group_id} domain",
        "description": f"Each artifact in this group deals as the archive for snapshots of one ontology of the DBpedia Archivo - A Web-Scale Interface for Ontology Archiving under Consumer-oriented Aspects. Find out more at http://archivo.dbpedia.org.",
    }

    databus_version_id = DatabusVersionIdentifier(
        user=archivo_config.DATABUS_USER,
        group=group_id,
        artifact=artifact_id,
        version=version_id,
    )

    # generate new version
    data_writer = FileWriter(
        path_base=archivo_config.LOCAL_PATH,
        target_url_base=archivo_config.PUBLIC_URL_BASE,
    )
    archivo_version = ArchivoVersion(
        confirmed_ontology_id=ontology_id_uri,
        crawling_result=crawling_result,
        parsing_result=parsing_result_turtle,
        databus_version_identifier=databus_version_id,
        access_date=access_date,
        data_writer=data_writer,
        logger=logger,
        source=source,
        test_suite=test_suite,
    )

    try:
        archivo_version.deploy(generate_files=True, group_info=group_info)
        logger.info(f"Successfully deployed the new update of ontology {uri}")
        process_log.append(
            ProcessStepLog(
                status=LogLevel.INFO,
                stepname="Deployment to Databus",
                message=f"Sucessfully deployed to the Databus: <a href={archivo_config.DATABUS_BASE}/{archivo_config.DATABUS_USER}/{group_id}/{artifact_id}>{archivo_config.DATABUS_BASE}/{archivo_config.DATABUS_USER}/{group_id}/{artifact_id}</a>",
            )
        )
        return archivo_version
    except Exception as e:
        logger.error("There was an Error deploying to the databus")
        logger.error(str(e))
        process_log.append(
            ProcessStepLog(
                status=LogLevel.ERROR,
                stepname="Deployment to Databus",
                message=f"Failed to deploy to the Databus. Reason: {str(e)}.\n\nThere is probably an error on the Databus site, if this error persists please create an issue in the github repository.",
            )
        )
        return None


def handle_track_this_uri(
    original_nir: str,
    dev_version_location: str,
    data_writer: DataWriter,
    test_suite: TestSuite,
    logger: Logger,
    process_log: List[ProcessStepLog] = None,
) -> Optional[ArchivoVersion]:

    # check robot if we are allowed to crawl
    if not perform_robot_check(dev_version_location, process_log, logger):
        return None

    # now fetch the rdf data
    crawling_result = determine_best_content_type(
        dev_version_location, user_output=process_log
    )

    access_date = datetime.now()
    version_id = access_date.strftime("%Y.%m.%d-%H%M%S")

    if crawling_result is None:
        return None

    # all it needs to be is readable by rdflib, so try parsing it

    parsing_result_turtle = parsing.parse_rdf_from_string(
        crawling_result.response.text,
        original_nir,
        crawling_result.rdf_type,
        RDF_Type.TURTLE,
    )

    try:
        onto_graph = graph_handling.get_graph_of_string(
            parsing_result_turtle.parsed_rdf, RDF_Type.TURTLE
        )
    except Exception:
        logger.error(
            f"Exception in rdflib parsing of URI {dev_version_location}", exc_info=True
        )
        process_log.append(
            ProcessStepLog(
                status=LogLevel.ERROR,
                stepname="Load Graph in rdflib",
                message=f"RDFlib couldn't parse the file of {dev_version_location}. Reason: {traceback.format_exc()}",
            )
        )
        return None

    # now it is parseable rdf it can be deployed as dev version

    # overwrite generated databus identifiers
    group_id, artifact_id = string_tools.generate_databus_identifier_from_uri(
        original_nir, dev=True
    )

    databus_version_id = DatabusVersionIdentifier(
        user=archivo_config.DATABUS_USER,
        group=group_id,
        artifact=artifact_id,
        version=version_id,
    )

    archivo_version = ArchivoVersion(
        confirmed_ontology_id=original_nir,
        crawling_result=crawling_result,
        parsing_result=parsing_result_turtle,
        databus_version_identifier=databus_version_id,
        access_date=access_date,
        data_writer=data_writer,
        logger=logger,
        source="DEV",
        test_suite=test_suite,
        dev_uri=dev_version_location,
    )

    try:
        archivo_version.deploy(generate_files=True)
        logger.info(
            f"Successfully deployed the new update of DEV ontology for {original_nir}"
        )
        process_log.append(
            ProcessStepLog(
                status=LogLevel.INFO,
                stepname="Deployment to Databus",
                message=f"Sucessfully deployed to the Databus: <a href={archivo_config.DATABUS_BASE}/{archivo_config.DATABUS_USER}/{group_id}/{artifact_id}>{archivo_config.DATABUS_BASE}/{archivo_config.DATABUS_USER}/{group_id}/{artifact_id}</a>",
            )
        )
        return archivo_version
    except Exception as e:
        logger.error("There was an Error deploying to the databus")
        logger.error(str(e))
        process_log.append(
            ProcessStepLog(
                status=LogLevel.ERROR,
                stepname="Deployment to Databus",
                message=f"Failed to deploy to the Databus. Reason: {str(e)}.\n\nThere is probably an error on the Databus site, if this error persists please create an issue in the github repository.",
            )
        )
        return None
