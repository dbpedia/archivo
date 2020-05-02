import subprocess
from rdflib import compare
import inspectVocabs
import stringTools
import requests
import crawlURIs
from datetime import datetime
import os
import json
import generatePoms
import sys
import re
import ontoFiles

semanticVersionRegex=re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

def graphDiff(oldGraph, newGraph):
    oldIsoGraph = compare.to_isomorphic(oldGraph)
    newIsoGraph = compare.to_isomorphic(newGraph)
    return compare.graph_diff(oldIsoGraph, newIsoGraph)

def checkForNewVersion(vocab_uri, oldETag, oldLastMod, oldContentLength, bestHeader):
  # when both of the old values are not compareable, always download and check
  if stringTools.isNoneOrEmpty(oldETag) and stringTools.isNoneOrEmpty(oldLastMod) and stringTools.isNoneOrEmpty(oldContentLength):
    return True
  acc_header = {'Accept': bestHeader}
  try:
    response = requests.head(vocab_uri, headers=acc_header, timeout=30, allow_redirects=True)
    if response.status_code < 400:
      newETag = stringTools.getEtagFromResponse(response)
      newLastMod = stringTools.getLastModifiedFromResponse(response)
      newContentLength = stringTools.getContentLengthFromResponse(response)
      if oldETag == newETag and oldLastMod == newLastMod and oldContentLength == newContentLength:
        return False
      else:
        return True
    else:
      return None
  except requests.exceptions.TooManyRedirects:
        print("Too many redirects, cancel parsing...")
        return None
  except TimeoutError:
        print("Timed out: "+vocab_uri)
        return None
  except requests.exceptions.ConnectionError:
        print("Bad Connection "+ vocab_uri)
        return None
  except requests.exceptions.ReadTimeout:
        print("Connection timed out for URI ", vocab_uri)
        return None


def localDiffAndRelease(uri, localDiffDir, bestHeader, fallout_index, latestVersionDir, lastSemVersion):
  try:
    artifactDir, latestVersion = os.path.split(latestVersionDir)
    groupDir, artifactName = os.path.split(artifactDir)
    print("Found different headers, downloading and parsing to compare...")
    success, sourcePath, response = crawlURIs.downloadSource(uri, localDiffDir, "tmpSource", bestHeader)
    accessDate = datetime.now().strftime("%Y.%m.%d; %H:%M:%S")
    if not success:
      print("Uri not reachable")
      fallout_index.append((uri, True, "Couldnt download file"))
      return
    ontoFiles.parseRDFSource(sourcePath, os.path.join(localDiffDir, "tmpSourceParsed.ttl"), "turtle", deleteEmpty=True, silent=True, sourceUri=uri)
    if not os.path.isfile(os.path.join(localDiffDir, "tmpSourceParsed.ttl")): 
      print("File not parseable")
      fallout_index.append((uri, True, "Unparseable new File"))
      return
    oldGraph = inspectVocabs.getGraphOfVocabFile(os.path.join(latestVersionDir, artifactName + "_type=parsed.ttl"))
    newGraph = inspectVocabs.getGraphOfVocabFile(os.path.join(localDiffDir, "tmpSourceParsed.ttl"))
    both, old, new = graphDiff(oldGraph, newGraph)
    if len(old) == 0 and len(new) == 0:
      print("Not different")
      stringTools.deleteAllFilesInDir(localDiffDir)
    else:
      print("Different!")
      # generating new semantic version
      oldSuccess, oldAxioms = getAxiomsOfOntology(os.path.join(latestVersionDir, artifactName + "_type=parsed.nt"))
      newSuccess, newAxioms = getAxiomsOfOntology(os.path.join(localDiffDir, "tmpSourceParsed.ttl"))
      if oldSuccess and newSuccess:
        newSemVersion = getNewSemanticVersion(lastSemVersion, oldAxioms, newAxioms)
      else:
        print("Couldn't generate a new Semantic Version, keeping the old...")
        newSemVersion = lastSemVersion
      new_version = datetime.now().strftime("%Y.%m.%d-%H%M%S")
      newVersionPath = os.path.join(artifactDir, new_version)
      os.makedirs(newVersionPath, exist_ok=True)
      fileExt = os.path.splitext(sourcePath)[1]
      os.rename(sourcePath, os.path.join(newVersionPath, artifactName + "_type=orig" + fileExt))
      crawlURIs.generateNewRelease(uri, newVersionPath, artifactName, os.path.join(newVersionPath, artifactName + "_type=orig" + fileExt), bestHeader, response, accessDate, semVersion=newSemVersion)
      stringTools.deleteAllFilesInDir(localDiffDir)
      print(generatePoms.callMaven(os.path.join(artifactDir, "pom.xml"), "validate"))
  except FileNotFoundError:
    print("Error: Couldn't find file for", uri)



def handleDiffForUri(uri, rootdir, fallout_index):
  localDiffDir = os.path.join(rootdir, ".tmpDiffDir")
  if not os.path.isdir(localDiffDir):
    os.mkdir(localDiffDir)
  groupId, artifact = stringTools.generateGroupAndArtifactFromUri(uri)
  artifactDir = os.path.join(rootdir, groupId, artifact)
  if not os.path.isdir(artifactDir):
    print("No data for this uri", uri)
    return
  versionDirs = [dir for dir in os.listdir(artifactDir) if os.path.isdir(os.path.join(artifactDir, dir)) and dir != "target"]
  versionDirs.sort(reverse=True)
  latestVersion = versionDirs[0]
  latestVersionDir = os.path.join(artifactDir, latestVersion)
  print("Found latest version:", latestVersionDir)
  if os.path.isfile(os.path.join(latestVersionDir, artifact + "_type=meta.json")):
    with open(os.path.join(latestVersionDir, artifact + "_type=meta.json"), "r")as jsonFile:
      metadata = json.load(jsonFile)
  else:
    print("No metadata", groupId, artifact)
    return

  oldETag = metadata["E-Tag"]
  oldLastMod = metadata["lastModified"]
  bestHeader = metadata["best-header"]
  contentLength = metadata["content-length"]
  semVersion = metadata["semantic-version"]

  if bestHeader == "":
    return

  isDiff = checkForNewVersion(uri, oldETag, oldLastMod, contentLength, bestHeader)

  if isDiff == None:
    fallout_index.append((uri, True, "Unreachable ontology"))
    print("Couldnt access ontology", uri)
    return
  if isDiff:
    print("Fond potential different version for", uri)
    localDiffAndRelease(uri, localDiffDir, bestHeader, fallout_index, latestVersionDir, semVersion)
  else:
    print("No different version for", uri)


def getAxiomsOfOntology(ontologyPath):
  displayAxiomsPath = os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "DisplayAxioms.jar")

  process = subprocess.Popen(["java", "-jar", displayAxiomsPath, ontologyPath], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

  stdout, stderr= process.communicate()

  axiomSet = stdout.decode("utf8").split("\n")
  print("Returncode:", process.returncode)
  if process.returncode == 0:
    success = True
  else:
    success = False
    print(stderr.decode("utf-8"))
  
  return success, set([axiom.strip() for axiom in axiomSet if axiom.strip() != ""])


def getNewSemanticVersion(oldSemanticVersion, oldAxiomSet, newAxiomSet, silent=False):
  match = semanticVersionRegex.match(oldSemanticVersion)
  if match == None:
    print("Bad format of semantic version", oldSemanticVersion)
    return oldSemanticVersion
  
  major = int(match.group(1))
  minor = int(match.group(2))
  patch = int(match.group(3))

  both = oldAxiomSet.intersection(newAxiomSet)
  old = oldAxiomSet - newAxiomSet
  new = newAxiomSet - oldAxiomSet

  print("Old:", old)
  print("New:", new)


  if old == set() and new == set():
    return f"{str(major)}.{str(minor)}.{str(patch+1)}"
  elif new != set() and old == set():
    return f"{str(major)}.{str(minor+1)}.{str(0)}"
  else:
    return f"{str(major+1)}.{str(0)}.{str(0)}"
