from logging import Logger
from os.path import isfile
from typing import Dict, List, Optional, Tuple

import hashlib

import databusclient
import requests
import os
import sys
import traceback
from datetime import datetime

from databusclient.client import DeployError
from rdflib import Graph
from requests import Response

from archivo.crawling.ArchivoVersion import ArchivoVersion
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse, urldefrag, quote
from rdflib.term import Literal, URIRef
from string import Template
from SPARQLWrapper import SPARQLWrapper, JSON

from archivo.utils import stringTools, ontoFiles, archivoConfig, inspectVocabs, async_rdf_retrieval


# determine_best_content_type
# function used by
#
def determine_best_content_type(uri, user_output=None, logger=None):
    if user_output is None:
        user_output = []
    header_dict = {}
    for header in stringTools.rdfHeadersMapping:
        response, error = download_rdf_string(uri, acc_header=header)
        if error is None:
            try:
                triple_number, rapper_errors = ontoFiles.get_triples_from_rdf_string(
                    response.text, uri, input_type=stringTools.rdfHeadersMapping[header]
                )
            except Exception as e:
                if logger is not None:
                    logger.warning(
                        f"Couldn't parse {uri} with header {header}: {str(e)}"
                    )
                continue
            if triple_number is not None and triple_number > 0:
                user_output.append(
                    {
                        "status": True,
                        "step": f"Parsing with header {header}",
                        "message": f"Triples: {str(triple_number)}",
                    }
                )
                header_dict[header] = (response, triple_number)

                # break for really large ontologies
                if triple_number > 200000:
                    break
            else:
                if len(rapper_errors) > 20:
                    rapper_errors = rapper_errors[:20]
                user_output.append(
                    {
                        "status": False,
                        "step": f"Parsing with header {header}",
                        "message": "Triples: {} \n{}".format(
                            str(triple_number), "\n".join(rapper_errors[:20])
                        ),
                    }
                )
        else:
            user_output.append(
                {
                    "status": False,
                    "step": f"Parsing with header {header}",
                    "message": f"{error}",
                }
            )
    if header_dict == {}:
        return None, None, None
    best_header = [
        k
        for k, v in sorted(
            header_dict.items(), key=lambda item: item[1][1], reverse=True
        )
    ][0]
    resp, triple_number = header_dict[best_header]
    return best_header, resp, triple_number


def download_rdf_string(uri, acc_header, encoding="utf-8"):
    try:
        headers = {"Accept": acc_header}
        response = requests.get(uri, headers=headers, timeout=30, allow_redirects=True)
        if encoding is not None:
            response.encoding = encoding
        if response.status_code < 400:
            return response, None
        else:
            return response, "Not Accessible - Status " + str(response.status_code)
    except KeyboardInterrupt:
        sys.exit(19)
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
        return None, str(e)


def checkRobot(uri):
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


def downloadSource(uri, path, name, accHeader, encoding="utf-8"):
    try:
        acc_header = {"Accept": accHeader}
        response = requests.get(
            uri, headers=acc_header, timeout=30, allow_redirects=True
        )
        if encoding is not None:
            response.encoding = encoding
        fileEnding = stringTools.getFileEnding(response)
        filePath = path + os.sep + name + "_type=orig" + fileEnding
        if response.status_code < 400:
            with open(filePath, "w+") as ontfile:
                print(response.text, file=ontfile)
            return True, filePath, response
        else:
            return (
                False,
                filePath,
                "Not Accessible - Status " + str(response.status_code),
            )
    except requests.exceptions.TooManyRedirects as e:
        return False, "", str(e)
    except TimeoutError as e:
        return False, "", str(e)
    except requests.exceptions.ConnectionError as e:
        return False, "", str(e)
    except requests.exceptions.ReadTimeout as e:
        return False, "", str(e)
    except KeyboardInterrupt:
        sys.exit(19)
    except Exception as e:
        traceback.print_exc(file=sys.stdout)
        return False, "", str(e)


# returns the NIR if frgmant-equivalent, else None
def check_NIR(uri, graph, output=None):
    if output is None:
        output = []
    candidates = inspectVocabs.get_ontology_URIs(graph)

    if candidates == []:
        output.append(
            {
                "status": False,
                "step": "Determine non-information resource",
                "message": "Neither can't find a triple with <code>owl:Ontology</code> or <code>skos:ConceptScheme</code> as value",
            }
        )
        return False, None

    found_nir = None

    for nir in candidates:
        if stringTools.check_uri_equality(uri, nir):
            found_nir = nir

    if found_nir is None:
        output.append(
            {
                "status": False,
                "step": "Determine non-information resource",
                "message": f"Neither of {str(candidates)} equals the source URI {uri}, trying to validate {candidates[0]}",
            }
        )
        return False, candidates[0]
    else:
        output.append(
            {
                "status": True,
                "step": "Determine non-information resource",
                "message": f"Found non-information resource: {found_nir}",
            }
        )
        return True, found_nir


def handle_slash_uris(real_ont_uri: str, fetch_response: Response, graph: Graph, best_header: str,
                      user_output: List[Dict], logger: Logger) -> Tuple[Optional[str], List[Tuple[str, str]]]:
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
        input_type=stringTools.rdfHeadersMapping[best_header],
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
            output_type=stringTools.rdfHeadersMapping[best_header],
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


def perform_robot_check(vocab_uri: str, user_output: List[Dict], logger: Logger) -> bool:
    allowed, message = checkRobot(vocab_uri)
    logger.info(f"Robot allowed: {allowed}")
    if not allowed:
        logger.warning(f"{archivoConfig.archivo_agent} not allowed")
        user_output.append(
            {
                "status": False,
                "step": "Robot allowed check",
                "message": f"Archivo-Agent {archivoConfig.archivo_agent} is not allowed to access the ontology at <a href={vocab_uri}>{vocab_uri}</a>",
            }
        )
        return False
    else:
        user_output.append(
            {
                "status": True,
                "step": "Robot allowed check",
                "message": f"Archivo-Agent {archivoConfig.archivo_agent} is allowed.",
            }
        )
        return True


def handleNewUri(
        vocab_uri, index, dataPath, source, isNIR, testSuite, logger, user_output=None, recursion_depth=0
) -> Tuple[bool, bool, Optional[ArchivoVersion]]:
    if user_output is None:
        user_output = list()
    # remove fragment
    vocab_uri = urldefrag(vocab_uri)[0]
    # testing uri validity
    logger.info(f"Trying to validate {vocab_uri}")
    groupId, artifact = stringTools.generateGroupAndArtifactFromUri(vocab_uri)
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

    foundURI = stringTools.get_uri_from_index(vocab_uri, index)
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
    bestHeader, response, triple_number = determine_best_content_type(
        vocab_uri, user_output=user_output
    )

    version = datetime.now().strftime("%Y.%m.%d-%H%M%S")
    if bestHeader is None:
        user_output.append(
            {
                "status": False,
                "step": "Find Best Header",
                "message": "No RDF content detectable.",
            }
        )
        return False, isNIR, None

    accessDate = datetime.now()
    user_output.append(
        {
            "status": True,
            "step": "Find Best Header",
            "message": f"Best Header: {bestHeader} with {triple_number} triples",
        }
    )

    # generating the graph and runnning the queries
    try:
        graph = inspectVocabs.get_graph_of_string(response.text, bestHeader)
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
        ont_succ, real_ont_uri = check_NIR(vocab_uri, graph, output=user_output)
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
        real_ont_uri = inspectVocabs.getDefinedByUri(graph)
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
        if not stringTools.check_uri_equality(vocab_uri, str(real_ont_uri)):
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
                    recursion_depth=recursion_depth + 1
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
                recursion_depth=recursion_depth + 1
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

    groupId, artifact = stringTools.generateGroupAndArtifactFromUri(real_ont_uri)
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

    foundURI = stringTools.get_uri_from_index(real_ont_uri, index)
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
        additional_ntriple_content, retrieval_errors_by_uri = handle_slash_uris(real_ont_uri, response, graph,
                                                                                bestHeader, user_output, logger)

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
            "description"] = f"Each artifact in this group deals as the archive for snapshots of one ontology of the DBpedia Archivo - A Web-Scale Interface for Ontology Archiving under Consumer-oriented Aspects. Find out more at http://archivo.dbpedia.org. The description for the individual files in the artifact can be found here."

    newVersionPath = os.path.join(dataPath, groupId, artifact, version)
    os.makedirs(newVersionPath, exist_ok=True)

    # prepare new release
    fileExt = stringTools.file_ending_mapping[bestHeader]
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
        accessDate,
        bestHeader,
        logger,
        source,
        retrieval_errors=retrival_errors,
        user_output=user_output,
    )
    new_version.generateFiles()
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
    allowed, message = checkRobot(sourceURI)
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
        _ = inspectVocabs.get_graph_of_string(response.text, bestHeader)
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

    groupId, artifact = stringTools.generateGroupAndArtifactFromUri(nir, dev=True)
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
    fileExt = stringTools.file_ending_mapping[bestHeader]
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
        devURI=sourceURI,
    )
    new_version.generateFiles()
    new_version.generatePomAndDoc()

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
