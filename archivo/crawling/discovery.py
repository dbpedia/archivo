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
from archivo.models.databus_identifier import DatabusVersionIdentifier
from archivo.models.user_interaction import ProcessStepLog, LogLevel
from archivo.utils import (
    string_tools,
    ontoFiles,
    archivoConfig,
    graph_handling,
    async_rdf_retrieval,
    parsing,
)

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
    if rp.can_fetch(archivoConfig.archivo_agent, uri):
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


def handle_slash_uris(
    real_ont_uri: str,
    fetch_response: Response,
    graph: Graph,
    best_header: str,
    user_output: List[Dict],
    logger: Logger,
) -> Tuple[Optional[str], List[Tuple[str, str]]]:
    """Handles the slash uris by concurrently fetching the RDF data from the slashes. Returns an Optional[str] of N-Triples
    if successfull and a list of errors"""

    (
        nt_content_list,
        retrieval_error_list,
    ) = async_rdf_retrieval.gather_linked_content(
        real_ont_uri, graph, best_header, concurrent_requests=50, logger=logger
    )

    # get nt content from response
    (orig_nt_content, _, _, _,) = ontoFiles.parse_rdf_from_string(
        fetch_response.text,
        real_ont_uri,
        input_type=string_tools.rdfHeadersMapping[best_header],
        output_type="ntriples",
    )

    if len(nt_content_list) > 0:
        # append original nt content to retrieved content
        nt_content_list.append(orig_nt_content)

        # set parsed, concatted content as the original content
        (
            parsed_triples,
            triple_count,
            rapper_errors,
            _,
        ) = ontoFiles.parse_rdf_from_string(
            "\n".join(nt_content_list),
            real_ont_uri,
            input_type="ntriples",
            output_type=string_tools.rdfHeadersMapping[best_header],
        )
        if len(retrieval_error_list) > 0:
            user_output.append(
                {
                    "status": False,
                    "step": "Retrieve defined RDF content",
                    "message": "This ontology was recognized as a Slash Ontology, but there were errors with the defined RDF content:\n{}".format(
                        "\n".join([", ".join(tp) for tp in retrieval_error_list])
                    ),
                }
            )
        else:
            user_output.append(
                {
                    "status": True,
                    "step": "Retrieve defined RDF content",
                    "message": "This ontology was recognized as a Slash Ontology and {} different sources were included".format(
                        len(nt_content_list)
                    ),
                }
            )
        return parsed_triples, retrieval_error_list
    else:
        return None, retrieval_error_list


def perform_robot_check(
    vocab_uri: str, user_output: List[ProcessStepLog], logger: Logger
) -> bool:
    allowed, message = check_robot(vocab_uri)
    logger.info(f"Robot allowed: {allowed}")
    if not allowed:
        logger.warning(f"{archivoConfig.archivo_agent} not allowed")
        user_output.append(
            ProcessStepLog(
                status=LogLevel.ERROR,
                stepname="Robot allowance check",
                message=f"Archivo-Agent {archivoConfig.archivo_agent} is not allowed to access the ontology at <a href={vocab_uri}>{vocab_uri}</a>",
            )
        )
        return False
    else:
        user_output.append(
            ProcessStepLog(
                status=LogLevel.INFO,
                stepname="Robot allowance check",
                message=f"Archivo-Agent {archivoConfig.archivo_agent} is allowed.",
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
            if recursion_depth <= archivoConfig.max_recursion_depth:
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
                        message=f"Maximum recursion depth of {archivoConfig.max_recursion_depth} reached",
                    )
                )
                return None


def discover_new_uri(
    uri: str,
    vocab_uri_cache: List[str],
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
        user=archivoConfig.DATABUS_USER,
        group=group_id,
        artifact=artifact_id,
        version=version_id,
    )

    # generate new version

    archivo_version = ArchivoVersion(
        confirmed_ontology_id=ontology_id_uri,
        crawling_result=crawling_result,
        parsing_result=parsing_result_turtle,
        databus_version_identifier=databus_version_id,
    )


def handleNewUri(
    vocab_uri,
    index,
    dataPath,
    source,
    isNIR,
    testSuite,
    logger,
    user_output=None,
    recursion_depth=0,
) -> Tuple[bool, bool, Optional[ArchivoVersion]]:
    if user_output is None:
        user_output = list()
    # remove fragment
    vocab_uri = urldefrag(vocab_uri)[0]
    # testing uri validity
    logger.info(f"Trying to validate {vocab_uri}")
    groupId, artifact = string_tools.generate_databus_identifier_from_uri(vocab_uri)
    if groupId is None or artifact is None:
        logger.warning(f"Malformed Uri {vocab_uri}")
        user_output.append(
            {
                "status": False,
                "step": "URI check",
                "message": f"ERROR: Malformed URI {vocab_uri}",
            }
        )
        return False, isNIR, None

    foundURI = string_tools.get_uri_from_index(vocab_uri, index)
    if foundURI is not None:
        logger.info("Already known uri, skipping...")
        user_output.append(
            {
                "status": True,
                "step": "Index check",
                "message": f"This Ontology is already in the Archivo index and can be found at <a href=/info?o={quote(foundURI)}>here</a>",
            }
        )
        return False, isNIR, None

    # check robots.txt access

    if not perform_robot_check(vocab_uri, user_output, logger):
        return False, isNIR, None

    # load the best header with response and triple number
    crawling_result = determine_best_content_type(vocab_uri, user_output=user_output)

    if crawling_result is None:
        user_output.append(
            {
                "status": False,
                "step": "Find Best Header",
                "message": "No RDF content detectable.",
            }
        )
        return False, isNIR, None

    access_date = datetime.now()
    version = access_date.strftime("%Y.%m.%d-%H%M%S")

    user_output.append(
        {
            "status": True,
            "step": "Find Best Header",
            "message": f"Best Header: {crawling_result} with {crawling_result.triple_number} triples",
        }
    )

    # generating the graph and runnning the queries
    try:
        graph = inspectVocabs.get_graph_of_string(
            crawling_result.response.text, crawling_result
        )
    except Exception:
        logger.error(f"Exception in rdflib parsing of URI {vocab_uri}", exc_info=True)
        user_output.append(
            {
                "status": False,
                "step": "Load Graph in rdflib",
                "message": f"RDFlib couldn't parse the file of {vocab_uri}. Reason: {traceback.format_exc()}",
            }
        )
        return False, isNIR, None

    try:
        ont_succ, real_ont_uri = check_ontology_id_uri(
            vocab_uri, graph, output=user_output
        )
    except Exception:
        user_output.append(
            {
                "status": False,
                "step": "Determine non-information resource",
                "message": traceback.format_exc(),
            }
        )
        return False, isNIR, None

    if not ont_succ and real_ont_uri is None:
        # if no or no different ontology URI -> check defined_by
        real_ont_uri = graph_handling.get_defined_by_uri(graph)
        if real_ont_uri is None:
            logger.info("No Ontology discoverable")
            user_output.append(
                {
                    "status": False,
                    "step": "Looking for linked ontologies",
                    "message": "The given URI does not contain a <code>rdfs:isDefinedBy</code> or <code>skos:inScheme</code> triple",
                }
            )
            return False, isNIR, None
        if not string_tools.check_uri_equality(vocab_uri, str(real_ont_uri)):
            user_output.append(
                {
                    "status": True,
                    "step": "Looking for linked ontologies",
                    "message": f"Found linked URI: {real_ont_uri}",
                }
            )

            if recursion_depth <= archivoConfig.max_recursion_depth:

                return handleNewUri(
                    str(real_ont_uri),
                    index,
                    dataPath,
                    testSuite=testSuite,
                    source=source,
                    isNIR=True,
                    logger=logger,
                    user_output=user_output,
                    recursion_depth=recursion_depth + 1,
                )
            else:
                user_output.append(
                    {
                        "status": False,
                        "step": "Looking for linked ontologies",
                        "message": f"recursive discovery of content exceeded the number {archivoConfig.max_recursion_depth}",
                    }
                )
                return False, isNIR, None
        else:
            user_output.append(
                {
                    "status": False,
                    "step": "Looking for linked ontologies",
                    "message": "This RDF document is linked to itself via <code>rdfs:isDefinedBy</code> or <code>skos:inScheme</code>, but does not contain a triple with <code>owl:Ontology</code> or <code>skos:ConceptScheme</code>, so it can't be recognized as an ontology.",
                }
            )
            return False, isNIR, None
    elif not ont_succ and real_ont_uri is not None:
        # when another URI was discovered -> check it
        isNIR = True
        if recursion_depth <= archivoConfig.max_recursion_depth:

            return handleNewUri(
                str(real_ont_uri),
                index,
                dataPath,
                testSuite=testSuite,
                source=source,
                isNIR=True,
                logger=logger,
                user_output=user_output,
                recursion_depth=recursion_depth + 1,
            )

        else:
            user_output.append(
                {
                    "status": False,
                    "step": "Looking for linked ontologies",
                    "message": f"recursive discovery of content exceeded the number {archivoConfig.max_recursion_depth}",
                }
            )
            return False, isNIR, None

    # here we go if the uri is NIR and  its resolveable
    isNIR = True

    if isNIR and vocab_uri != real_ont_uri:
        logger.warning(f"unexpected value for real uri: {real_ont_uri}")

    groupId, artifact = string_tools.generate_databus_identifier_from_uri(real_ont_uri)
    if groupId is None or artifact is None:
        logger.warning(f"Malformed Uri {vocab_uri}")
        user_output.append(
            {
                "status": False,
                "step": "URI Check",
                "message": f"Malformed Uri {vocab_uri}",
            }
        )
        return False, isNIR, None

    foundURI = string_tools.get_uri_from_index(real_ont_uri, index)
    if foundURI is not None:
        logger.info(f"Already known uri {real_ont_uri}")
        user_output.append(
            {
                "status": True,
                "step": "Index check",
                "message": f"This Ontology is already in the Archivo index and can be found at <a href=/info?o={quote(foundURI)}>here</a>",
            }
        )
        return False, isNIR, None

    # handle slash uris

    retrival_errors = []
    if real_ont_uri.endswith("/"):
        additional_ntriple_content, retrieval_errors_by_uri = handle_slash_uris(
            real_ont_uri, response, graph, crawling_result.rdf_type, user_output, logger
        )

        # add the errors to the retrival errors list
        for tup in retrieval_errors_by_uri:
            retrival_errors.append(", ".join(tup))

        if additional_ntriple_content:
            orig_rdf_content = additional_ntriple_content
        else:
            orig_rdf_content = response.text
    else:
        orig_rdf_content = response.text

    group_info = {}

    # if it is a new group -> generate group info
    if not os.path.isdir(os.path.join(dataPath, groupId)):
        group_info["title"] = f"DBpedia Archivo ontologies from the {groupId} domain"
        group_info[
            "description"
        ] = f"Each artifact in this group deals as the archive for snapshots of one ontology of the DBpedia Archivo - A Web-Scale Interface for Ontology Archiving under Consumer-oriented Aspects. Find out more at http://archivo.dbpedia.org. The description for the individual files in the artifact can be found here."

    newVersionPath = os.path.join(dataPath, groupId, artifact, version)
    os.makedirs(newVersionPath, exist_ok=True)

    # prepare new release
    fileExt = string_tools.file_ending_mapping[crawling_result]
    new_orig_file_path = os.path.join(
        newVersionPath, artifact + "_type=orig." + fileExt
    )
    with open(new_orig_file_path, "w+") as new_orig_file:
        print(orig_rdf_content, file=new_orig_file)
    # new release
    logger.info("Generate new release files...")
    new_version = ArchivoVersion(
        real_ont_uri,
        new_orig_file_path,
        response,
        testSuite,
        access_date,
        crawling_result,
        logger,
        source,
        retrieval_errors=retrival_errors,
        user_output=user_output,
    )
    new_version.generate_files()
    databus_dataset_jsonld = new_version.build_databus_jsonld(group_info)

    logger.info("Deploying the data to the databus...")

    try:
        databusclient.deploy(databus_dataset_jsonld, archivoConfig.DATABUS_API_KEY)
        logger.info(f"Successfully deployed the new ontology {vocab_uri}")
        user_output.append(
            {
                "status": True,
                "step": "Deploy to DBpedia Databus",
                "message": f"Deployed the Ontology to the DBpedia Databus, should be accessable at <a href=https://databus.dbpedia.org/ontologies/{groupId}/{artifact}>https://databus.dbpedia.org/ontologies/{groupId}/{artifact}</a> soon",
            }
        )
        return True, isNIR, new_version
    except databusclient.client.DeployError as e:
        logger.error("There was an Error deploying to the databus")
        user_output.append(
            {"status": False, "step": "Deploy to DBpedia Databus", "message": str(e)}
        )
        logger.error(str(e))
        return False, isNIR, None


def handleDevURI(nir, sourceURI, dataPath, testSuite, logger, user_output=None):
    # remove fragment
    if user_output is None:
        user_output = list()
    sourceURI = urldefrag(sourceURI)[0]
    # testing uri validity
    logger.info(f"Trying to validate {sourceURI}")

    # check robots.txt access
    allowed, message = check_robot(sourceURI)
    logger.info(f"Robot allowed: {allowed}")
    if not allowed:
        logger.warning(f"{archivoConfig.archivo_agent} not allowed")
        user_output.append(
            {
                "status": False,
                "step": "Robot allowed check",
                "message": f"Archivo-Agent {archivoConfig.archivo_agent} is not allowed to access the ontology at <a href={sourceURI}>{sourceURI}</a>",
            }
        )
        return False, None

    user_output.append(
        user_output.append(
            {
                "status": True,
                "step": "Robot allowed check",
                "message": f"Archivo-Agent {archivoConfig.archivo_agent} is allowed.",
            }
        )
    )
    # load the best header with response and triple number
    bestHeader, response, triple_number = determine_best_content_type(
        nir, user_output=user_output
    )

    version = datetime.now().strftime("%Y.%m.%d-%H%M%S")
    if bestHeader is None:
        user_output.append(
            {
                "status": False,
                "step": "Find Best Header",
                "message": f"No RDF content detectable.",
            }
        )
        return False, None

    accessDate = datetime.now()

    # generating the graph and runnning the queries
    try:
        _ = graph_handling.get_graph_of_string(response.text, bestHeader)
    except Exception:
        logger.error("Exception in rdflib parsing", exc_info=True)
        user_output.append(
            {
                "status": False,
                "step": "Load Graph in rdflib",
                "message": f"RDFlib couldn't parse the file of {nir}. Reason: {traceback.format_exc()}",
            }
        )
        return False, None

    # here we go if the uri is NIR and  its resolveable

    groupId, artifact = string_tools.generate_databus_identifier_from_uri(nir, dev=True)
    if groupId is None or artifact is None:
        logger.warning(f"Malformed Uri {sourceURI}")
        user_output.append(
            user_output.append(
                {
                    "status": False,
                    "step": "URI Check",
                    "message": f"Malformed Uri {str(nir)}",
                }
            )
        )
        return False, None

    newVersionPath = os.path.join(dataPath, groupId, artifact, version)
    os.makedirs(newVersionPath, exist_ok=True)
    # prepare new release
    fileExt = string_tools.file_ending_mapping[bestHeader]
    new_orig_file_path = os.path.join(
        newVersionPath, artifact + "_type=orig." + fileExt
    )
    with open(new_orig_file_path, "w+") as new_orig_file:
        print(response.text, file=new_orig_file)
    # new release
    logger.info("Generate new release files...")
    new_version = ArchivoVersion(
        nir,
        os.path.join(newVersionPath, artifact + "_type=orig." + fileExt),
        response,
        testSuite,
        accessDate,
        bestHeader,
        logger,
        "DEV",
        user_output=user_output,
        dev_uri=sourceURI,
    )
    new_version.generate_files()

    logger.info("Deploying the data to the databus...")
    databus_dataset_jsonld = new_version.build_databus_jsonld()

    try:
        databusclient.deploy(databus_dataset_jsonld, archivoConfig.DATABUS_API_KEY)
        logger.info(f"Successfully deployed the new dev ontology {sourceURI}")
        user_output.append(
            {
                "status": True,
                "step": "Deploy to DBpedia Databus",
                "message": f"Deployed the Ontology to the DBpedia Databus, should be accessable at <a href=https://databus.dbpedia.org/ontologies/{groupId}/{artifact}>https://databus.dbpedia.org/ontologies/{groupId}/{artifact}</a> soon",
            }
        )
        return True, new_version
    except databusclient.client.DeployError as e:
        logger.error("There was an Error deploying to the databus")
        user_output.append(
            {"status": False, "step": "Deploy to DBpedia Databus", "message": str(e)}
        )
        logger.error(str(e))
        return False, None
