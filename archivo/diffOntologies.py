import subprocess
from rdflib import compare
from utils import inspectVocabs, ontoFiles
import requests
import crawlURIs
from datetime import datetime
import os
import json
import sys
import re
import uuid
from utils import ontoFiles, generatePoms, stringTools, queryDatabus, archivoConfig, docTemplates
from utils.archivoLogs import diff_logger
from string import Template

semanticVersionRegex=re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

myenv = os.environ.copy()
myenv['LC_ALL'] = 'C'

def graphDiff(oldGraph, newGraph):
    oldIsoGraph = compare.to_isomorphic(oldGraph)
    newIsoGraph = compare.to_isomorphic(newGraph)
    return compare.graph_diff(oldIsoGraph, newIsoGraph)

def getSortedNtriples(sourceFile, targetPath, vocab_uri, inputType=None):
  try:
    if inputType == None:
      rapperProcess = subprocess.run(["rapper", "-g", "-I", vocab_uri, sourceFile, "-o", "ntriples"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      nTriples = rapperProcess.stdout
    elif inputType == "ntriples":
      with open(sourceFile, "rb") as ntriplesFile:
        nTriples = ntriplesFile.read()
    else:
      rapperProcess = subprocess.run(["rapper", "-i", inputType, "-I", vocab_uri, sourceFile, "-o", "ntriples"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      nTriples = rapperProcess.stdout
    with open(targetPath, "w+") as sortedNtriples:
      sortProcess = subprocess.run(["sort", "-u"], input=nTriples, stdout=sortedNtriples, stderr=subprocess.PIPE, env=myenv)
      sortErrors = sortProcess.stderr.decode("utf-8")
    if os.stat(targetPath).st_size == 0:
      diff_logger.error("Error in parsing file, no triples returned")
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
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=myenv)
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
      return False, [line.strip() for line in oldTriples if line.strip() != ""], [line.strip() for line in newTriples if line != ""]
  except Exception:
    diff_logger.error("Exeption during diffing with comm", exc_info=True)

def checkForNewVersion(vocab_uri, oldETag, oldLastMod, oldContentLength, bestHeader):
  diff_logger.info(f"Checking the header for {vocab_uri}")
  # when both of the old values are not compareable, always download and check
  if stringTools.isNoneOrEmpty(oldETag) and stringTools.isNoneOrEmpty(oldLastMod) and stringTools.isNoneOrEmpty(oldContentLength):
    return True, None
  acc_header = {'Accept': bestHeader}
  try:
    response = requests.head(vocab_uri, headers=acc_header, timeout=30, allow_redirects=True)
    if response.status_code < 400:
      newETag = stringTools.getEtagFromResponse(response)
      newLastMod = stringTools.getLastModifiedFromResponse(response)
      newContentLength = stringTools.getContentLengthFromResponse(response)
      if oldETag == newETag and oldLastMod == newLastMod and oldContentLength == newContentLength:
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


def localDiffAndRelease(uri, localDiffDir, oldNtriples, bestHeader, latestVersionDir, lastSemVersion, testSuite, devURI=""):
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
    diff_logger.info("Found different headers, downloading and parsing to compare...")
    new_version = datetime.now().strftime("%Y.%m.%d-%H%M%S")
    newVersionPath = os.path.join(artifactDir, new_version)
    os.makedirs(newVersionPath, exist_ok=True)
    newBestHeader, headerErrors = crawlURIs.determineBestAccHeader(locURI, localDiffDir)
    if newBestHeader == None:
      diff_logger.warning(f" {locURI} Couldn't parse new version")
      diff_logger.warning(headerErrors)
      return None, "\n".join(headerErrors), None
    success, sourcePath, response = crawlURIs.downloadSource(locURI, newVersionPath, artifactName, newBestHeader, encoding="utf-8")
    accessDate = datetime.now().strftime("%Y.%m.%d; %H:%M:%S")
    if not success:
      diff_logger.warning("Uri not reachable")
      stringTools.deleteAllFilesInDirAndDir(newVersionPath)
      return None, response, None
    #ontoFiles.parseRDFSource(sourcePath, os.path.join(localDiffDir, "tmpSourceParsed.nt"), "ntriples", deleteEmpty=True, silent=True, sourceUri=uri)
    errors, warnings = getSortedNtriples(sourcePath, os.path.join(localDiffDir, "newVersionSorted.nt"), uri, inputType=crawlURIs.rdfHeadersMapping[newBestHeader])
    if not os.path.isfile(os.path.join(localDiffDir, "newVersionSorted.nt")) or errors != "": 
      diff_logger.error("File not parseable")
      stringTools.deleteAllFilesInDirAndDir(localDiffDir)
      return None, f"Couldn't parse File: {errors}", None
    getSortedNtriples(oldNtriples, os.path.join(localDiffDir, "oldVersionSorted.nt"), uri, inputType="ntriples")
    isEqual, oldTriples, newTriples = commDiff(os.path.join(localDiffDir, "oldVersionSorted.nt"), os.path.join(localDiffDir, "newVersionSorted.nt"))
    diff_logger.debug("Old Triples:" + "\n".join(oldTriples))
    diff_logger.debug("New Triples:" + "\n".join(newTriples))
    #if len(old) == 0 and len(new) == 0:
    if isEqual:
      diff_logger.info("No new version")
      stringTools.deleteAllFilesInDirAndDir(localDiffDir)
      stringTools.deleteAllFilesInDirAndDir(newVersionPath)
      return False, "No new Version", None
    else:
      diff_logger.info("New Version!")
      # generating new semantic version
      oldSuccess, oldAxioms = testSuite.getAxiomsOfOntology(os.path.join(localDiffDir, "oldVersionSorted.nt"))
      newSuccess, newAxioms = testSuite.getAxiomsOfOntology(os.path.join(localDiffDir, "newVersionSorted.nt"))
      if oldSuccess and newSuccess:
        newSemVersion, oldAxioms, newAxioms = getNewSemanticVersion(lastSemVersion, oldAxioms, newAxioms)
      else:
        diff_logger.error("Couldn't generate the axioms, no new semantic version")
        diff_logger.debug("Old Axioms:"+str(oldAxioms))
        diff_logger.debug("New Axioms:"+str(newAxioms))
        if not oldSuccess and not newSuccess:
          newSemVersion = "ERROR: No Axioms for both versions"
        elif not oldSuccess:
          newSemVersion = "ERROR: No Axioms for old version"
        else:
          newSemVersion = "ERROR: No Axioms for new version"

      fileExt = os.path.splitext(sourcePath)[1]
      with open(os.path.join(newVersionPath, artifactName + "_type=diff_axioms=old.dl"), "w+") as oldAxiomsFile:
        print("\n".join(oldAxioms), file=oldAxiomsFile)
      with open(os.path.join(newVersionPath, artifactName + "_type=diff_axioms=new.dl"), "w+") as newAxiomsFile:
        print("\n".join(newAxioms), file=newAxiomsFile) 
      dbVersion = crawlURIs.generateNewRelease(uri, newVersionPath, artifactName, os.path.join(newVersionPath, artifactName + "_type=orig" + fileExt), newBestHeader, response, accessDate, semVersion=newSemVersion, testSuite=testSuite, logger=diff_logger)
      stringTools.deleteAllFilesInDirAndDir(localDiffDir)
      if not os.path.isfile(os.path.join(groupDir, "pom.xml")):
        with open(os.path.join(groupDir, "pom.xml"), "w+") as parentPomFile:
          pomString=generatePoms.generateParentPom(groupId=group,
                                            packaging="pom",
                                            modules=[],
                                            packageDirectory=archivoConfig.packDir,
                                            downloadUrlPath=archivoConfig.downloadUrl,
                                            publisher=archivoConfig.pub,
                                            maintainer=archivoConfig.pub,
                                            groupdocu=Template(docTemplates.groupDoc).safe_substitute(groupid=group),
                                            ) 
          print(pomString, file=parentPomFile)
      status, log = generatePoms.callMaven(os.path.join(artifactDir, "pom.xml"), "deploy")
      if status > 0:
        diff_logger.critical("Couldn't deploy new diff version")
        diff_logger.info(log)
        return None, "ERROR: Couldn't deploy to databus!", dbVersion
      else:
        return True, "OK", dbVersion
  except FileNotFoundError:
    diff_logger.critical(f"Couldn't find file for {uri}")
    stringTools.deleteAllFilesInDirAndDir(localDiffDir)
    return None, f"INTERNAL ERROR: Couldn't find file for {uri}"



def handleDiffForUri(uri, localDir, metafileUrl, lastNtURL, lastVersion, testSuite, devURI=""):
  if devURI != "":
    groupId, artifact = stringTools.generateGroupAndArtifactFromUri(uri, dev=True)
  else:
    groupId, artifact = stringTools.generateGroupAndArtifactFromUri(uri)
  artifactPath = os.path.join(localDir, groupId, artifact)
  lastVersionPath = os.path.join(artifactPath, lastVersion)
  lastMetaFile = os.path.join(lastVersionPath, artifact + "_type=meta.json")
  lastNtFile = os.path.join(lastVersionPath, lastNtURL.rpartition("/")[2])
  if not os.path.isfile(lastMetaFile):
    os.makedirs(lastVersionPath, exist_ok=True)
    try:
      metadata = requests.get(metafileUrl).json()
    except requests.exceptions.RequestException:
      diff_logger.error("There was an error downloading the latest metadata-file, skipping this ontology...")
      return None, "There was an error downloading the latest metadata-file, skipping this ontology...", None

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

  if devURI == "":
    isDiff, error = checkForNewVersion(uri, oldETag, oldLastMod, contentLength, bestHeader)
  else:
    isDiff, error = checkForNewVersion(devURI, oldETag, oldLastMod, contentLength, bestHeader)
  #isDiff = True
  localDiffDir = os.path.join(localDir, "." + uuid.uuid4().hex)
  if not os.path.isdir(localDiffDir):
    os.mkdir(localDiffDir)

  if isDiff == None:
    diff_logger.warning("Header Access: "+error)
    stringTools.deleteAllFilesInDirAndDir(localDiffDir)
    return None, "Header Access: "+error, None
  if isDiff:
    diff_logger.info(f"Fond potential different version for {uri}")
    return localDiffAndRelease(uri, localDiffDir, lastNtFile, bestHeader, lastVersionPath, semVersion, testSuite, devURI=devURI)
  else:
    stringTools.deleteAllFilesInDirAndDir(localDiffDir)
    diff_logger.info(f"No different version for {uri}")
    return False, f"No different version for {uri}", None


def getNewSemanticVersion(oldSemanticVersion, oldAxiomSet, newAxiomSet, silent=False):
  
  both = oldAxiomSet.intersection(newAxiomSet)
  old = oldAxiomSet - newAxiomSet
  new = newAxiomSet - oldAxiomSet

  diff_logger.info("Old:\n"+"\n".join(old))
  diff_logger.info("New:\n"+"\n".join(new))

  match = semanticVersionRegex.match(oldSemanticVersion)
  if match == None:
    diff_logger.error(f"Bad format of semantic version: {oldSemanticVersion}")
    return "ERROR: Can't build new semantic version because last is broken", old, new
  
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
  #success, sourcePath, response = crawlURIs.downloadSource("http://www.georss.org/georss/", ".", "georss", "application/rdf+xml", encoding="utf-8")
  isDiff, errors = checkForNewVersion("http://bag.basisregistraties.overheid.nl/def/bag", "vdnuisb", "", "", "application/rdf+xml")
  print(isDiff)
  print(errors)