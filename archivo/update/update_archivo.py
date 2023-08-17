from dataclasses import dataclass
from logging import Logger
import subprocess
from pathlib import Path
from typing import Tuple, List, Set, Optional, Dict

from archivo.crawling.archivo_version import ArchivoVersion
from archivo.models import content_negotiation
from archivo.models.data_writer import DataWriter
import databusclient
from rdflib import compare
import requests
from archivo.crawling import discovery
from datetime import datetime
import os
import json
import re
from archivo.utils import (
    ontoFiles,
    string_tools,
    archivoConfig,
    docTemplates,
    async_rdf_retrieval,
    graph_handling,
    validation,
    parsing,
)
from archivo.utils.ArchivoExceptions import (
    UnavailableContentException,
    UnparseableRDFException,
)
from archivo.utils.archivoLogs import diff_logger
from archivo.models.databus_identifier import (
    DatabusVersionIdentifier,
    DatabusFileMetadata,
)
from archivo.utils.validation import TestSuite
from archivo.utils.parsing import RapperParsingResult, RapperParsingInfo

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


def getSortedNtriples(
    sourceFile, targetPath, vocab_uri, inputType=None, logger=diff_logger
):
    try:
        if inputType is None:
            rapperProcess = subprocess.run(
                ["rapper", "-g", "-I", vocab_uri, sourceFile, "-o", "ntriples"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            nTriples = rapperProcess.stdout
        elif inputType == "ntriples":
            with open(sourceFile, "rb") as ntriplesFile:
                nTriples = ntriplesFile.read()
        else:
            rapperProcess = subprocess.run(
                [
                    "rapper",
                    "-i",
                    inputType,
                    "-I",
                    vocab_uri,
                    sourceFile,
                    "-o",
                    "ntriples",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            nTriples = rapperProcess.stdout
            errors, warnings = ontoFiles.parse_rapper_errors(
                rapperProcess.stderr.decode("utf-8")
            )
            if errors != []:
                return errors, warnings

        # run sort process
        with open(targetPath, "w+") as sortedNtriples:
            sortProcess = subprocess.run(
                ["sort", "-u"],
                input=nTriples,
                stdout=sortedNtriples,
                stderr=subprocess.PIPE,
                env=__ENVIRONMENT,
            )
            sortErrors = sortProcess.stderr.decode("utf-8")
        if not os.path.isfile(targetPath) or os.stat(targetPath).st_size == 0:
            logger.warning("Error in parsing file, no triples returned")
            if os.path.isfile(targetPath):
                os.remove(targetPath)

        if sortErrors != "":
            logger.error(f"An error in sorting triples occured: {sortErrors}")

        if inputType != "ntriples":
            return ontoFiles.parse_rapper_errors(rapperProcess.stderr.decode("utf-8"))
        else:
            return [], []
    except Exception as e:
        logger.error("Exeption during parsing and sorting", exc_info=True)
        return [str(e)], []


def contains_ignored_props(line):
    for prop in archivoConfig.ignore_props:
        if prop in line:
            return True
    return False


def diff_content(old_triples: List[str], new_triples: List[str]) -> DiffResult:
    """Checks the diff with python builtins. Also handles deduplication and empty lines. Returns a DiffResult"""

    def filterfun(x: str):
        """Kicking out empty lines"""
        return x.strip() != ""

    old_set_filtered = set(filter(filterfun, set(old_triples)))
    new_set_filtered = set(filter(filterfun, set(new_triples)))

    new_triples = new_set_filtered - old_set_filtered
    old_triples = old_set_filtered - new_set_filtered

    is_diff = not old_triples and not new_triples

    return DiffResult(
        is_diff,
        "\n".join(old_triples),
        "\n".join(new_triples),
        old_triples,
        new_triples,
    )


def comm_diff(oldFile, newFile, logger=diff_logger):
    command = ["comm", "-3", oldFile, newFile]
    try:
        oldTriples = []
        newTriples = []
        process = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=__ENVIRONMENT
        )
        diffErrors = process.stderr.decode("utf-8")
        commOutput = process.stdout.decode("utf-8")
        if diffErrors != "":
            logger.error(f"Error in diffing with comm: {diffErrors}")
        commLines = commOutput.split("\n")
        for line in commLines:
            if line.strip() == "":
                continue
            if line.startswith("\t") and not contains_ignored_props(line):
                newTriples.append(line)
            elif not contains_ignored_props(line):
                oldTriples.append(line)

        if oldTriples == [] and newTriples == []:
            return True, oldTriples, newTriples
        else:
            return (
                False,
                [line.strip() for line in oldTriples if line.strip() != ""],
                [line.strip() for line in newTriples if line != ""],
            )
    except Exception:
        logger.error("Exeption during diffing with comm", exc_info=True)


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
        turtle_parsing_result.parsed_rdf, "text/turtle"
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


def get_old_nt_content(
    local_path_base: Optional[str], nt_file_metadata: DatabusFileMetadata
) -> str:
    # check if the old file can be loaded from disk
    local_file_path = Path(f"{local_path_base}/{nt_file_metadata}")

    if local_path_base and local_file_path.is_file():
        with open(local_file_path) as old_nt_file:
            return old_nt_file.read()
    else:
        old_file_resp = requests.get(f"{archivoConfig.DATABUS_BASE}/{nt_file_metadata}")

        if old_file_resp.status_code >= 400:
            raise UnavailableContentException(old_file_resp)
        else:
            return old_file_resp.text


def diff_check_new_file(
    uri: str,
    old_metadata: Dict,
    old_nt_file_path: Optional[str],
    dev_uri: Optional[str],
    logger: Logger,
) -> Tuple[Optional[DiffResult], str]:

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

    if not uri.endswith("/") and not has_new_version:
        # if there are no possible further values, we are done
        return None, ""

    output = []

    newBestHeader, response, triple_number = discovery.determine_best_content_type(
        locURI, user_output=output
    )

    if newBestHeader is None:
        error_str = "\n".join(
            [d.get("step", "None") + "  " + d.get("message", "None") for d in output]
        )
        logger.warning(f"{locURI} Couldn't parse new version")
        logger.warning(error_str)
        raise UnavailableContentException(error_str)

    parsing_result = (
        handle_slash_uris(uri, bestHeader, response, logger)
        if uri.endswith("/")
        else parsing.parse_rdf_from_string(
            response.text,
            uri,
            input_type=content_negotiation.get_rdf_type(newBestHeader),
            output_type=content_negotiation.RDF_Type.N_TRIPLES,
        )
    )

    original_content = parsing_result.parsed_rdf if uri.endswith("/") else response.text

    # raising an exception if there are no triples in the result
    if parsing_result.parsing_info.triple_number <= 0:
        raise UnparseableRDFException("\n".join(parsing_result.parsing_info.errors))

    # TODO: this needs to be accessible even remote
    with open(old_nt_file_path) as old_nt_file:
        old_file_nt_content = old_nt_file.read()

    old_content_triples = "\n".split(old_file_nt_content)
    new_content_triples = "\n".split(parsing_result.parsed_rdf)

    diff_result = diff_content(old_content_triples, new_content_triples)

    return diff_result, original_content


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
    last_metafile_url: str,
    last_nt_file_url: str,
    last_version_timestamp: str,
    data_writer: DataWriter,
    test_suite: TestSuite,
    dev_uri: Optional[str],
    logger: Logger = diff_logger,
) -> Tuple[bool, str, Optional[ArchivoVersion]]:
    try:
        metadata, old_nt_path, old_version_id = prepare_diff_for_ontology(
            uri=uri,
            last_metafile_url=last_metafile_url,
            last_ntriples_url=last_nt_file_url,
            last_version_timestamp=last_version_timestamp,
            data_writer=data_writer,
            dev_uri=dev_uri,
        )
        diff_result, original_content = diff_check_new_file(
            uri=uri,
            dev_uri=dev_uri,
            logger=logger,
            old_metadata=metadata,
            old_nt_file_path=old_nt_path,
        )
    except Exception as e:
        return False, str(e), None

    if not diff_result.is_diff:
        return False, f"No different version for {uri}", None
    # New version!

    new_version_identifier = DatabusVersionIdentifier(
        archivoConfig.DATABUS_USER,
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
        confirmed_nir=uri,
    )


def localDiffAndRelease(
    uri,
    oldNtriples,
    bestHeader,
    latestVersionDir,
    lastSemVersion,
    testSuite,
    source,
    old_triples,
    devURI="",
    logger=diff_logger,
):
    try:
        if devURI == "":
            isDev = False
            locURI = uri
        else:
            isDev = True
            locURI = devURI
        artifactDir, latestVersion = os.path.split(latestVersionDir)
        groupDir, artifactName = os.path.split(artifactDir)
        _, group = os.path.split(groupDir)
        logger.info("Found different headers, downloading and parsing to compare...")
        new_version = datetime.now().strftime("%Y.%m.%d-%H%M%S")
        newVersionPath = os.path.join(artifactDir, new_version)
        os.makedirs(newVersionPath, exist_ok=True)
        # load the best header with rdf_string and triple number
        output = []
        newBestHeader, response, triple_number = discovery.determine_best_content_type(
            locURI, user_output=output
        )

        if newBestHeader is None:
            error_str = "\n".join(
                [
                    d.get("step", "None") + "  " + d.get("message", "None")
                    for d in output
                ]
            )
            logger.warning(f"{locURI} Couldn't parse new version")
            logger.warning(error_str)
            return None, error_str, None

        # change the encoding to utf-8
        response.encoding = "utf-8"
        sourcePath = os.path.join(
            newVersionPath,
            artifactName
            + "_type=orig."
            + string_tools.file_ending_mapping[newBestHeader],
        )

        # This message is used to show errors of the linked data content gathering
        # even if it was successfull
        success_error_message = None

        if uri.endswith("/"):
            # check if URI is slash URI -> retrieve linked content
            # this is still under development and not perfect
            # i.e. currently there is no way of reducing an ontology, since it checks wether the ontology is increased
            (
                orig_turtle_content,
                _,
                rapper_errors,
                _,
            ) = ontoFiles.parse_rdf_from_string(
                response.text,
                uri,
                input_type=string_tools.rdfHeadersMapping[newBestHeader],
                output_type="turtle",
            )

            if rapper_errors != []:
                return None, "\n".join(rapper_errors), None

            graph = graph_handling.get_graph_of_string(
                orig_turtle_content, "text/turtle"
            )
            nt_list, retrieval_errors = async_rdf_retrieval.gather_linked_content(
                uri,
                graph,
                pref_header=newBestHeader,
                concurrent_requests=50,
                logger=logger,
            )

            if retrieval_errors:
                error_str = "Failed retrieval for content:\n" + "\n".join(
                    [" -- ".join(tp) for tp in retrieval_errors]
                )
                logger.warning(error_str)
                success_error_message = error_str

            (orig_nt_content, _, _, _,) = ontoFiles.parse_rdf_from_string(
                response.text,
                uri,
                input_type=string_tools.rdfHeadersMapping[newBestHeader],
                output_type="ntriples",
            )
            if len(nt_list) > 0:
                # append original nt content to retrieved content
                nt_list.append(orig_nt_content)

                triple_set = set()

                # deduplicate ntriples
                for nt_str in nt_list:
                    for triple in nt_str.split("\n"):
                        if triple.strip() != "":
                            triple_set.add(triple)

                (
                    parsed_triples,
                    triple_count,
                    rapper_errors,
                    _,
                ) = ontoFiles.parse_rdf_from_string(
                    "\n".join(triple_set),
                    uri,
                    input_type="ntriples",
                    output_type=string_tools.rdfHeadersMapping[newBestHeader],
                )

                with open(sourcePath, "w+") as new_orig_file:
                    print(parsed_triples, file=new_orig_file)
            else:
                with open(sourcePath, "w+") as new_orig_file:
                    print(response.text, file=new_orig_file)
        else:
            with open(sourcePath, "w+") as new_orig_file:
                print(response.text, file=new_orig_file)

        accessDate = datetime.now().strftime("%Y.%m.%d; %H:%M:%S")
        new_sorted_nt_path = os.path.join(
            newVersionPath, artifactName + "_type=parsed_sorted.nt"
        )
        errors, warnings = getSortedNtriples(
            sourcePath,
            new_sorted_nt_path,
            uri,
            inputType=string_tools.rdfHeadersMapping[newBestHeader],
            logger=logger,
        )
        if not os.path.isfile(new_sorted_nt_path) or errors != []:
            logger.warning(f"File of {uri} not parseable")
            logger.warning(errors)
            string_tools.deleteAllFilesInDirAndDir(newVersionPath)
            return None, f"Couldn't parse File: {errors}", None
        old_sorted_nt_path = os.path.join(newVersionPath, "oldVersionSorted.nt")
        getSortedNtriples(
            oldNtriples, old_sorted_nt_path, uri, inputType="ntriples", logger=logger
        )
        isEqual, oldTriples, newTriples = comm_diff(
            old_sorted_nt_path, new_sorted_nt_path, logger=logger
        )
        # if len(old) == 0 and len(new) == 0:
        if isEqual:
            logger.info("No new version")
            string_tools.deleteAllFilesInDirAndDir(newVersionPath)
            return False, "No new Version", None
        else:
            logger.info("New Version!")
            # generating new semantic version
            oldSuccess, oldAxioms = testSuite.getAxiomsOfOntology(old_sorted_nt_path)
            newSuccess, newAxioms = testSuite.getAxiomsOfOntology(new_sorted_nt_path)
            if oldSuccess and newSuccess:
                newSemVersion, oldAxioms, newAxioms = build_new_semantic_version(
                    lastSemVersion, oldAxioms, newAxioms
                )
            else:
                logger.warning("Couldn't generate the axioms, no new semantic version")
                # logger.debug("Old Axioms:" + str(oldAxioms))
                # logger.debug("New Axioms:" + str(newAxioms))
                if not oldSuccess and not newSuccess:
                    newSemVersion = "ERROR: No Axioms for both versions"
                elif not oldSuccess:
                    newSemVersion = "ERROR: No Axioms for old version"
                else:
                    newSemVersion = "ERROR: No Axioms for new version"

            os.remove(old_sorted_nt_path)
            with open(
                os.path.join(newVersionPath, artifactName + "_type=diff_axioms=old.dl"),
                "w+",
            ) as oldAxiomsFile:
                print("\n".join(oldAxioms), file=oldAxiomsFile)
            with open(
                os.path.join(newVersionPath, artifactName + "_type=diff_axioms=new.dl"),
                "w+",
            ) as newAxiomsFile:
                print("\n".join(newAxioms), file=newAxiomsFile)
            with open(
                os.path.join(
                    newVersionPath, artifactName + "_type=diff_triples=old.nt"
                ),
                "w+",
            ) as old_diff_file:
                print("\n".join(oldTriples), file=old_diff_file)
            with open(
                os.path.join(
                    newVersionPath, artifactName + "_type=diff_triples=new.nt"
                ),
                "w+",
            ) as new_diff_file:
                print("\n".join(newTriples), file=new_diff_file)

            new_version = discovery.ArchivoVersion(
                uri,
                sourcePath,
                response,
                testSuite,
                accessDate,
                newBestHeader,
                logger,
                source,
                semantic_version=newSemVersion,
                dev_uri=devURI,
            )
            new_version.generate_files()

            databus_dataset_jsonld = new_version.build_databus_jsonld()

            logger.info("Deploying the data to the databus...")

            try:
                databusclient.deploy(
                    databus_dataset_jsonld, archivoConfig.DATABUS_API_KEY
                )
                logger.info(f"Successfully deployed the new update of ontology {uri}")
                return True, success_error_message, new_version
            except Exception as e:
                logger.error("There was an Error deploying to the databus")
                logger.error(str(e))
                return False, "ERROR: Couldn't deploy to databus!", new_version

    except FileNotFoundError:
        logger.exception(f"Couldn't find file for {uri}")
        return None, f"INTERNAL ERROR: Couldn't find file for {uri}", None


def prepare_diff_for_ontology(
    uri: str,
    last_metafile_url: str,
    last_ntriples_url: str,
    last_version_timestamp: str,
    data_writer: DataWriter,
    dev_uri: Optional[str] = None,
    local_path: str = None,
) -> Tuple[Dict, str, DatabusVersionIdentifier]:
    """Prepares the local structure for the diff"""

    groupId, artifact = string_tools.generate_databus_identifier_from_uri(
        uri, dev=bool(dev_uri)
    )

    artifactPath = os.path.join(local_path, groupId, artifact)
    lastVersionPath = os.path.join(artifactPath, last_version_timestamp)
    last_meta_file_path = os.path.join(lastVersionPath, artifact + "_type=meta.json")
    last_nt_file_path = os.path.join(
        lastVersionPath, last_ntriples_url.rpartition("/")[2]
    )

    old_db_verison_id = DatabusVersionIdentifier(
        user="ontologies",
        group=groupId,
        artifact=artifact,
        version=last_version_timestamp,
    )

    if not os.path.isfile(last_meta_file_path):
        os.makedirs(lastVersionPath, exist_ok=True)
        metadata = requests.get(last_metafile_url).json()

        old_metadata_file_metadata = DatabusFileMetadata(
            old_db_verison_id,
            sha_256_sum="",
            content_length=-1,
            content_variants={"type": "meta"},
            file_extension="json",
            compression=None,
        )

        data_writer.write_databus_file(
            json.dumps(metadata, indent=4, sort_keys=True),
            old_metadata_file_metadata,
            log_file=False,
        )

        with open(last_meta_file_path, "w+") as latestMetaFile:
            json.dump(metadata, latestMetaFile, indent=4, sort_keys=True)
    else:
        with open(last_meta_file_path, "r") as latestMetaFile:
            metadata = json.load(latestMetaFile)

    if not os.path.isfile(last_nt_file_path):
        oldOntologyResponse = requests.get(last_ntriples_url)
        oldOntologyResponse.encoding = "utf-8"

        if oldOntologyResponse.status_code >= 400:
            raise UnavailableContentException(oldOntologyResponse)

        old_nt_file_metadata = DatabusFileMetadata(
            old_db_verison_id,
            sha_256_sum="",
            content_length=-1,
            content_variants={"type": "parsed"},
            file_extension="nt",
            compression=None,
        )

        data_writer.write_databus_file(
            oldOntologyResponse.text, old_nt_file_metadata, log_file=False
        )

    return metadata, last_nt_file_path, old_db_verison_id


def handleDiffForUri(
    uri: str,
    data_writer: DataWriter,
    metafileUrl: str,
    lastNtURL: str,
    last_version_timestamp: str,
    test_suite: validation.TestSuite,
    source: str,
    dev_uri: str = "",
    logger: Logger = diff_logger,
) -> Tuple[bool, str, Optional[ArchivoVersion]]:
    try:
        metadata, last_nt_file_path = prepare_diff_for_ontology(
            uri,
            metafileUrl,
            lastNtURL,
            last_version_timestamp,
            dev_uri=dev_uri,
            local_path=archivoConfig.localPath,
            logger=logger,
        )
    except Exception as e:
        message = f"Could not prepare for diff: {e}"
        return False, message, None

    oldETag = metadata["http-data"]["e-tag"]
    oldLastMod = metadata["http-data"]["lastModified"]
    bestHeader = metadata["http-data"]["best-header"]
    contentLength = metadata["http-data"]["content-length"]
    semVersion = metadata["ontology-info"]["semantic-version"]
    old_triple_count = metadata["ontology-info"]["triples"]

    # this is for handling slash URIs explicitly with related content
    if uri.endswith("/"):
        # in the case of slash uris -> directly jump to the content diff
        is_diff = True
    else:
        # check headers if something changed
        try:
            is_diff = check_for_new_version(
                ontoLocationURI,
                oldETag,
                oldLastMod,
                contentLength,
                bestHeader,
            )
        except [UnavailableContentException, requests.TooManyRedirects] as e:
            logger.warning(e)
            return None, str(e), None

    if is_diff:
        logger.info(f"Fond potential different version for {ontoLocationURI}")
        return localDiffAndRelease(
            uri,
            lastNtFile,
            bestHeader,
            lastVersionPath,
            semVersion,
            test_suite,
            source,
            old_triple_count,
            devURI=dev_uri,
            logger=logger,
        )
    else:
        logger.info(f"No different version for {uri}")
        return False, f"No different version for {uri}", None


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


if __name__ == "__main__":
    from archivo.utils.validation import TestSuite
    import traceback

    ts = TestSuite()
    try:
        success, msg, archivoVersion = handleDiffForUri(
            "http://www.bbc.co.uk/ontologies/bbc",
            "./testdir/",
            "https://akswnc7.informatik.uni-leipzig.de/dstreitmatter/archivo/id.kb.se/vocab/2021.11.23-091502/vocab_type=meta.json",
            "http://akswnc7.informatik.uni-leipzig.de/dstreitmatter/archivo/bbc.co.uk/ontologies--bbc/2020.07.16-163437/ontologies--bbc_type=parsed.nt",
            "2021.11.23-091502",
            ts,
            "LOV",
        )
        print(success, msg)
    except:
        traceback.print_exc()
