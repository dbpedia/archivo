import subprocess
from typing import Tuple, List, Set

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
    stringTools,
    archivoConfig,
    docTemplates,
    async_rdf_retrieval,
    graph_handling,
)
from archivo.utils.ArchivoExceptions import UnavailableContentException
from archivo.utils.archivoLogs import diff_logger
from string import Template

__SEMANTIC_VERSION_REGEX = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

__ENVIRONMENT = os.environ.copy()
__ENVIRONMENT["LC_ALL"] = "C"


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


def containsIgnoredProps(line):
    for prop in archivoConfig.ignore_props:
        if prop in line:
            return True
    return False


def diff_content(old_triples: List[str], new_triples: List[str]) -> Tuple[List[str], List[str]]:
    old_set = set(old_triples)
    new_set = set(new_triples)

    return list(old_set - new_set), list(new_set - old_set)


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
            if line.startswith("\t") and not containsIgnoredProps(line):
                newTriples.append(line)
            elif not containsIgnoredProps(line):
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
        vocab_uri: str, old_e_tag: str, old_last_mod: str, old_content_length, best_header: str
) -> bool:
    """Check the location of the vocab with a HEAD request and check if new content is available.
    Returns true if new version is available, else false."""

    if (
        stringTools.is_none_or_empty(old_e_tag) and
        stringTools.is_none_or_empty(old_last_mod) and
        stringTools.is_none_or_empty(old_content_length)
    ):
        # if none of the old versions are compareable -> full download diff is always needed
        return True

    response = requests.head(
        vocab_uri, headers={"Accept": best_header}, timeout=30, allow_redirects=True
    )

    if response.status_code > 400:
        raise UnavailableContentException(response)

    new_e_tag = stringTools.getEtagFromResponse(response)
    new_last_mod = stringTools.getLastModifiedFromResponse(response)
    new_content_length = stringTools.getContentLengthFromResponse(response)
    if (
            old_e_tag == new_e_tag
            and old_last_mod == new_last_mod
            and old_content_length == new_content_length
    ):
        return False
    else:
        return True






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
            + stringTools.file_ending_mapping[newBestHeader],
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
                input_type=stringTools.rdfHeadersMapping[newBestHeader],
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
                input_type=stringTools.rdfHeadersMapping[newBestHeader],
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
                    output_type=stringTools.rdfHeadersMapping[newBestHeader],
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
            inputType=stringTools.rdfHeadersMapping[newBestHeader],
            logger=logger,
        )
        if not os.path.isfile(new_sorted_nt_path) or errors != []:
            logger.warning(f"File of {uri} not parseable")
            logger.warning(errors)
            stringTools.deleteAllFilesInDirAndDir(newVersionPath)
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
            stringTools.deleteAllFilesInDirAndDir(newVersionPath)
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
                databusclient.deploy(databus_dataset_jsonld, archivoConfig.DATABUS_API_KEY)
                logger.info(f"Successfully deployed the new update of ontology {uri}")
                return True, success_error_message, new_version
            except databusclient.client.DeployError as e:
                logger.error("There was an Error deploying to the databus")
                logger.error(str(e))
                return False, "ERROR: Couldn't deploy to databus!", new_version

    except FileNotFoundError:
        logger.exception(f"Couldn't find file for {uri}")
        return None, f"INTERNAL ERROR: Couldn't find file for {uri}", None


def handleDiffForUri(
    uri,
    localDir,
    metafileUrl,
    lastNtURL,
    lastVersion,
    testSuite,
    source,
    devURI="",
    logger=diff_logger,
):
    if devURI != "":
        groupId, artifact = stringTools.generate_databus_identifier_from_uri(uri, dev=True)
        ontoLocationURI = devURI
    else:
        groupId, artifact = stringTools.generate_databus_identifier_from_uri(uri)
        ontoLocationURI = uri
    artifactPath = os.path.join(localDir, groupId, artifact)
    lastVersionPath = os.path.join(artifactPath, lastVersion)
    lastMetaFile = os.path.join(lastVersionPath, artifact + "_type=meta.json")
    lastNtFile = os.path.join(lastVersionPath, lastNtURL.rpartition("/")[2])
    if not os.path.isfile(lastMetaFile):
        os.makedirs(lastVersionPath, exist_ok=True)
        try:
            metadata = requests.get(metafileUrl).json()
        except requests.exceptions.RequestException:
            logger.error(
                "There was an error downloading the latest metadata-file, skipping this ontology..."
            )
            return (
                None,
                "There was an error downloading the latest metadata-file, skipping this ontology...",
                None,
            )

        with open(lastMetaFile, "w+") as latestMetaFile:
            json.dump(metadata, latestMetaFile, indent=4, sort_keys=True)
    else:
        with open(lastMetaFile, "r") as latestMetaFile:
            metadata = json.load(latestMetaFile)

    if not os.path.isfile(lastNtFile):
        oldOntologyResponse = requests.get(lastNtURL)
        oldOntologyResponse.encoding = "utf-8"
        with open(lastNtFile, "w") as origFile:
            print(oldOntologyResponse.text, file=origFile)

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
            testSuite,
            source,
            old_triple_count,
            devURI=devURI,
            logger=logger,
        )
    else:
        logger.info(f"No different version for {uri}")
        return False, f"No different version for {uri}", None


def build_new_semantic_version(
    old_semantic_version: str, old_axiom_set: Set[str], new_axiom_set: Set[str], logger=diff_logger
):

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
        return f"{str(major)}.{str(minor)}.{str(patch+1)}", old, new
    elif new != set() and old == set():
        return f"{str(major)}.{str(minor+1)}.{str(0)}", old, new
    else:
        return f"{str(major+1)}.{str(0)}.{str(0)}", old, new


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
