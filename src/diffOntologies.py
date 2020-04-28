import ontoFiles
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


def runComm(oldFile, newFile):
    process = subprocess.Popen(["LC_ALL=C","comm", "-3", oldFile, newFile], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stout, stderr = process.communicate()

def sortFile(sourcePath, targetpath):
    with open(targetpath, "w+") as targetfile:
        process = subprocess.Popen(["LC_ALL=C", "sort", "-u"], stdout=targetfile, stderr=subprocess.PIPE)
        stderr = process.communicate()[1]

def graphDiff(oldGraph, newGraph):
    oldIsoGraph = compare.to_isomorphic(oldGraph)
    newIsoGraph = compare.to_isomorphic(newGraph)
    return compare.graph_diff(oldIsoGraph, newIsoGraph)

def checkForNewVersion(vocab_uri, oldETag, oldLastMod, oldContentLength, bestHeader):
  # when both of the old values are not compareable, always download and check
  if stringTools.isNoneOrEmpty(oldETag) and stringTools.isNoneOrEmpty(oldLastMod):
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


def localDiffAndRelease(uri, localDiffDir, bestHeader, fallout_index, latestVersionDir):
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
    new_version = datetime.now().strftime("%Y.%m.%d-%H%M%S")
    newVersionPath = os.path.join(artifactDir, new_version)
    os.makedirs(newVersionPath, exist_ok=True)
    fileExt = os.path.splitext(sourcePath)[1]
    os.rename(sourcePath, os.path.join(newVersionPath, artifactName + "_type=orig" + fileExt))
    crawlURIs.generateNewRelease(uri, newVersionPath, artifactName, os.path.join(newVersionPath, artifactName + "_type=orig" + fileExt), bestHeader, response, accessDate)
    stringTools.deleteAllFilesInDir(localDiffDir)
    print(generatePoms.callMaven(os.path.join(artifactDir, "pom.xml"), "deploy"))



def handleDiffForUri(uri, rootdir, fallout_index):
  localDiffDir = ".tmpDiffDir"
  if not os.path.isdir(localDiffDir):
    os.mkdir(localDiffDir)
  groupId, artifact = stringTools.generateGroupAndArtifactFromUri(uri)
  artifactDir = os.path.join(rootdir, groupId, artifact)
  if not os.path.isdir(artifactDir):
    print("No data for this uri", uri)
    return
  versionDirs = [dir for dir in os.listdir(artifactDir) if os.path.isdir(os.path.join(artifactDir, dir))]
  versionDirs.sort(reverse=True)
  latestVersion = versionDirs[0]
  latestVersionDir = os.path.join(artifactDir, latestVersion)
  print("Found latest version:", latestVersionDir)
  if os.path.isfile(os.path.join(latestVersionDir, artifact + "_type=meta.json")):
    with open(os.path.join(latestVersionDir, artifact + "_type=meta.json"), "r")as jsonFile:
      metadata = json.load(jsonFile)
  else:
    print("No metadata", groupId, artifactDir)
    return

  oldETag = metadata["E-Tag"]
  oldLastMod = metadata["lastModified"]
  bestHeader = metadata["best-header"]
  contentLength = metadata["content-length"]

  if bestHeader == "":
    return

  isDiff = checkForNewVersion(uri, oldETag, oldLastMod, contentLength, bestHeader)

  if isDiff == None:
    fallout_index.append((uri, True, "Unreachable ontology"))
    print("Couldnt access ontology", uri)
    return
  if isDiff:
    print("Fond potential different version for", uri)
    localDiffAndRelease(uri, localDiffDir, bestHeader, fallout_index, latestVersionDir)
  else:
    print("No different version for", uri)
