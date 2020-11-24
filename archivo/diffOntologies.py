import subprocess
from rdflib import compare
import requests
import crawlURIs
from datetime import datetime
import os
import json
import sys
import re
from utils import (
    ontoFiles,
    generatePoms,
    stringTools,
    queryDatabus,
    archivoConfig,
    docTemplates,
)
from utils.archivoLogs import diff_logger
from string import Template

semanticVersionRegex = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

myenv = os.environ.copy()
myenv["LC_ALL"] = "C"


def graphDiff(oldGraph, newGraph):
    oldIsoGraph = compare.to_isomorphic(oldGraph)
    newIsoGraph = compare.to_isomorphic(newGraph)
    return compare.graph_diff(oldIsoGraph, newIsoGraph)


def getSortedNtriples(sourceFile, targetPath, vocab_uri, inputType=None):
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

        with open(targetPath, "w+") as sortedNtriples:
            sortProcess = subprocess.run(
                ["sort", "-u"],
                input=nTriples,
                stdout=sortedNtriples,
                stderr=subprocess.PIPE,
                env=myenv,
            )
            sortErrors = sortProcess.stderr.decode("utf-8")
        if os.stat(targetPath).st_size == 0:
            diff_logger.warning("Error in parsing file, no triples returned")
            os.remove(targetPath)

        if sortErrors != "":
            diff_logger.error(f"An error in sorting triples occured: {sortErrors}")

        if inputType != "ntriples":
            return ontoFiles.returnRapperErrors(rapperProcess.stderr.decode("utf-8"))
        else:
            return None, None
    except Exception as e:
        diff_logger.error("Exeption during parsing and sorting", exc_info=True)
        return str(e), None


def containsIgnoredProps(line):
    for prop in archivoConfig.ignore_props:
        if prop in line:
            return True
    return False


def commDiff(oldFile, newFile):
    command = ["comm", "-3", oldFile, newFile]
    try:
        oldTriples = []
        newTriples = []
        process = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=myenv
        )
        diffErrors = process.stderr.decode("utf-8")
        commOutput = process.stdout.decode("utf-8")
        if diffErrors != "":
            diff_logger.error(f"Error in diffing with comm: {diffErrors}")
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
        diff_logger.error("Exeption during diffing with comm", exc_info=True)


def checkForNewVersion(vocab_uri, oldETag, oldLastMod, oldContentLength, bestHeader):
    diff_logger.info(f"Checking the header for {vocab_uri}")
    # when both of the old values are not compareable, always download and check
    if (
        stringTools.isNoneOrEmpty(oldETag)
        and stringTools.isNoneOrEmpty(oldLastMod)
        and stringTools.isNoneOrEmpty(oldContentLength)
    ):
        return True, None
    acc_header = {"Accept": bestHeader}
    try:
        response = requests.head(
            vocab_uri, headers=acc_header, timeout=30, allow_redirects=True
        )
        if response.status_code < 400:
            newETag = stringTools.getEtagFromResponse(response)
            newLastMod = stringTools.getLastModifiedFromResponse(response)
            newContentLength = stringTools.getContentLengthFromResponse(response)
            if (
                oldETag == newETag
                and oldLastMod == newLastMod
                and oldContentLength == newContentLength
            ):
                return False, None
            else:
                return True, None
        else:
            return None, f"No Access - Status {str(response.status_code)}"
    except requests.exceptions.TooManyRedirects:
        diff_logger.warning("Too many redirects, cancel parsing...")
        return None, "Too many redirects"
    except TimeoutError:
        diff_logger.warning(f"Timed out for {vocab_uri}")
        return None, "TimeOut Error"
    except requests.exceptions.ConnectionError:
        diff_logger.warning(f"Bad Connection for {vocab_uri}")
        return None, "Connection Error"
    except requests.exceptions.ReadTimeout:
        diff_logger.warning(f"Connection timed out for URI {vocab_uri}")
        return None, "Read Timeout"
    except:
        diff_logger.warning(f"Unkown Error occurred for URI {vocab_uri}")
        return None, "Unknown error"


def localDiffAndRelease(
    uri,
    oldNtriples,
    bestHeader,
    latestVersionDir,
    lastSemVersion,
    testSuite,
    source,
    devURI="",
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
        diff_logger.info(
            "Found different headers, downloading and parsing to compare..."
        )
        new_version = datetime.now().strftime("%Y.%m.%d-%H%M%S")
        newVersionPath = os.path.join(artifactDir, new_version)
        os.makedirs(newVersionPath, exist_ok=True)
        # load the best header with rdf_string and triple number
        output = []
        newBestHeader, response, triple_number = crawlURIs.determine_best_content_type(
            locURI, user_output=output
        )
        if newBestHeader is None:
            error_str = "\n".join(output)
            diff_logger.warning(f" {locURI} Couldn't parse new version")
            diff_logger.warning(error_str)
            return None, error_str, None
        sourcePath = os.path.join(
            newVersionPath,
            artifactName + "_type=orig." + crawlURIs.file_ending_mapping[newBestHeader],
        )
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
            inputType=crawlURIs.rdfHeadersMapping[newBestHeader],
        )
        if not os.path.isfile(new_sorted_nt_path) or errors is not []:
            diff_logger.warning(f"File of {uri} not parseable")
            diff_logger.warning(errors)
            stringTools.deleteAllFilesInDirAndDir(newVersionPath)
            return None, f"Couldn't parse File: {errors}", None
        old_sorted_nt_path = os.path.join(newVersionPath, "oldVersionSorted.nt")
        getSortedNtriples(oldNtriples, old_sorted_nt_path, uri, inputType="ntriples")
        isEqual, oldTriples, newTriples = commDiff(
            old_sorted_nt_path, new_sorted_nt_path
        )
        diff_logger.debug("Old Triples:" + "\n".join(oldTriples))
        diff_logger.debug("New Triples:" + "\n".join(newTriples))
        # if len(old) == 0 and len(new) == 0:
        if isEqual:
            diff_logger.info("No new version")
            stringTools.deleteAllFilesInDirAndDir(newVersionPath)
            return False, "No new Version", None
        else:
            diff_logger.info("New Version!")
            # generating new semantic version
            oldSuccess, oldAxioms = testSuite.getAxiomsOfOntology(old_sorted_nt_path)
            newSuccess, newAxioms = testSuite.getAxiomsOfOntology(new_sorted_nt_path)
            if oldSuccess and newSuccess:
                newSemVersion, oldAxioms, newAxioms = getNewSemanticVersion(
                    lastSemVersion, oldAxioms, newAxioms
                )
            else:
                diff_logger.warning(
                    "Couldn't generate the axioms, no new semantic version"
                )
                diff_logger.debug("Old Axioms:" + str(oldAxioms))
                diff_logger.debug("New Axioms:" + str(newAxioms))
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

            new_version = crawlURIs.ArchivoVersion(
                uri,
                sourcePath,
                response,
                testSuite,
                accessDate,
                newBestHeader,
                diff_logger,
                source,
                semanticVersion=newSemVersion,
                devURI=devURI,
            )
            new_version.generateFiles()
            new_version.generatePomAndDoc()

            if not os.path.isfile(os.path.join(groupDir, "pom.xml")):
                with open(os.path.join(groupDir, "pom.xml"), "w+") as parentPomFile:
                    pomString = generatePoms.generateParentPom(
                        groupId=group,
                        packaging="pom",
                        modules=[],
                        packageDirectory=archivoConfig.packDir,
                        downloadUrlPath=archivoConfig.downloadUrl,
                        publisher=archivoConfig.pub,
                        maintainer=archivoConfig.pub,
                        groupdocu=Template(docTemplates.groupDoc).safe_substitute(
                            groupid=group
                        ),
                    )
                    print(pomString, file=parentPomFile)
            status, log = generatePoms.callMaven(
                os.path.join(artifactDir, "pom.xml"), "deploy"
            )
            if status > 0:
                diff_logger.critical("Couldn't deploy new diff version")
                diff_logger.info(log)
                return None, "ERROR: Couldn't deploy to databus!", new_version
            else:
                return True, "OK", new_version
    except FileNotFoundError:
        diff_logger.critical(f"Couldn't find file for {uri}")
        return None, f"INTERNAL ERROR: Couldn't find file for {uri}", None


def handleDiffForUri(
    uri, localDir, metafileUrl, lastNtURL, lastVersion, testSuite, source, devURI=""
):
    if devURI != "":
        groupId, artifact = stringTools.generateGroupAndArtifactFromUri(uri, dev=True)
        ontoLocationURI = devURI
    else:
        groupId, artifact = stringTools.generateGroupAndArtifactFromUri(uri)
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
            diff_logger.error(
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

    isDiff, error = checkForNewVersion(
        ontoLocationURI, oldETag, oldLastMod, contentLength, bestHeader
    )

    if isDiff == None:
        diff_logger.warning("Header Access: " + error)
        return None, "Header Access: " + error, None
    if isDiff:
        diff_logger.info(f"Fond potential different version for {ontoLocationURI}")
        return localDiffAndRelease(
            uri,
            lastNtFile,
            bestHeader,
            lastVersionPath,
            semVersion,
            testSuite,
            source,
            devURI=devURI,
        )
    else:
        diff_logger.info(f"No different version for {uri}")
        return False, f"No different version for {uri}", None


def getNewSemanticVersion(oldSemanticVersion, oldAxiomSet, newAxiomSet, silent=False):

    both = oldAxiomSet.intersection(newAxiomSet)
    old = oldAxiomSet - newAxiomSet
    new = newAxiomSet - oldAxiomSet

    diff_logger.info("Old Axioms:\n" + "\n".join(old))
    diff_logger.info("New Axioms:\n" + "\n".join(new))

    match = semanticVersionRegex.match(oldSemanticVersion)
    if match is None:
        diff_logger.warning(f"Bad format of semantic version: {oldSemanticVersion}")
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
    from utils.validation import TestSuite
    import traceback

    ts = TestSuite(".")
    try:
        success, msg, archivoVersion = handleDiffForUri(
            "http://purl.org/cyber/misp",
            ".",
            "http://akswnc7.informatik.uni-leipzig.de/dstreitmatter/archivo/purl.allotrope.org/voc--afo--REC--2019--09--aft/2020.06.10-201508/voc--afo--REC--2019--09--aft_type=meta.json",
            "http://akswnc7.informatik.uni-leipzig.de/dstreitmatter/archivo/purl.allotrope.org/voc--afo--REC--2019--09--aft/2020.06.10-201508/voc--afo--REC--2019--09--aft_type=parsed.nt",
            "2020.06.10-201508",
            ts,
            "prefix.cc",
        )
    except:
        traceback.print_exc()
