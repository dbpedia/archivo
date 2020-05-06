import os
import sys
import json
import subprocess
import re
import csv
import stringTools
import inspectVocabs

rapperErrorsRegex=re.compile(r"^rapper: Error.*$")
rapperWarningsRegex=re.compile(r"^rapper: Warning.*$")
rapperTriplesRegex=re.compile(r"rapper: Parsing returned (\d+) triples")


def returnRapperErrors(rapperLog):
  errorMatches = []
  warningMatches = []
  for line in rapperLog.split("\n"):
    if rapperErrorsRegex.match(line):
      errorMatches.append(line)
    elif rapperWarningsRegex.match(line):
      warningMatches.append(line)
  return ";".join(errorMatches), ";".join(warningMatches)

def getTripleNumberFromRapperLog(rapperlog):
  match = rapperTriplesRegex.search(rapperlog)
  if match != None:
    return int(match.group(1))
  else:
    return None

#removes recursively all dirs that are empty or just contain empty files or directories
def deleteEmptyDirsRecursive(startpath):
  if os.path.isdir(startpath):
    for pathname in os.listdir(startpath):
      if os.path.isdir(startpath + os.sep + pathname):
        deleteEmptyDirsRecursive(startpath + os.sep + pathname)
      elif os.path.isfile(startpath + os.sep + pathname):
        if os.stat(startpath + os.sep + pathname).st_size == 0:
          os.remove(startpath + os.sep + pathname)
    if len(os.listdir(startpath)) == 0:
      os.rmdir(startpath)
  else:
    print(f"Not a directory: {startpath}")

def writeVocabInformation(pathToFile, definedByUri, lastModified, rapperErrors, rapperWarnings, etag, tripleSize, bestHeader, licenseViolationsBool, licenseWarningsBool, consistentWithImports, consistentWithoutImports, lodeConform, accessed, headerString, nirHeader, contentLenght, semVersion=None):
  vocabInformation={}
  vocabInformation["non-information-uri"] = definedByUri
  vocabInformation["accessed"] = accessed
  vocabInformation["lastModified"] = lastModified
  vocabInformation["rapperErrors"] = rapperErrors
  vocabInformation["rapperWarnings"] = rapperWarnings
  vocabInformation["E-Tag"] = etag
  vocabInformation["triples"] = tripleSize
  vocabInformation["best-header"] = bestHeader
  vocabInformation["License-I"] = licenseViolationsBool
  vocabInformation["License-II"] = licenseWarningsBool
  vocabInformation["consistent"] = consistentWithImports
  vocabInformation["consistent-without-imports"] = consistentWithoutImports
  vocabInformation["resource-header"] = headerString
  vocabInformation["NIR-header"] = nirHeader
  vocabInformation["content-length"] = contentLenght
  vocabInformation["lode-conform"] = lodeConform
  if semVersion != None:
    vocabInformation["semantic-version"] = semVersion

  with open(pathToFile, "w+") as outfile:
    json.dump(vocabInformation, outfile, indent=4, sort_keys=True)

def getParsedRdf(sourcefile, sourceUri=None, silent=True):
  if sourceUri == None:
    process = subprocess.Popen(["rapper", "-g", sourcefile, "-o", "rdfxml"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  else:
    process = subprocess.Popen(["rapper", "-I", sourceUri, "-g", sourcefile, "-o", "rdfxml"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  
  stdout, stderr=process.communicate()
  if not silent:
    print(stderr.decode("utf-8"))
  
  return stdout.decode("utf-8")

def parseRDFSource(sourcefile, filepath, outputType, sourceUri=None,deleteEmpty=True, silent=False):
  with open(filepath, "w+") as ontfile:
    if sourceUri == None:
      process = subprocess.Popen(["rapper", "-g", sourcefile, "-o", outputType], stdout=ontfile, stderr=subprocess.PIPE)
    else:
      process = subprocess.Popen(["rapper", "-I", sourceUri,"-g", sourcefile, "-o", outputType], stdout=ontfile, stderr=subprocess.PIPE)
    
    stderr=process.communicate()[1].decode("utf-8")
    if not silent:
      print(stderr)
  if deleteEmpty:
    returnedTriples = getTripleNumberFromRapperLog(stderr)
    if not silent:
      print("Returned Triples: ", returnedTriples)
    if returnedTriples == None or returnedTriples == 0:
      if not silent:
        print("Parsed file empty, deleting...")
      os.remove(filepath)
  return returnRapperErrors(stderr)

def getParsedTriples(filepath):
  process = subprocess.Popen(["rapper", "-c", "-g", filepath], stderr=subprocess.PIPE)
  try:
    stderr = process.communicate()[1].decode("utf-8")
  except UnicodeDecodeError:
    print("There was a decoding error at parsing " + filepath)
    return None
  return getTripleNumberFromRapperLog(stderr)

def loadIndexJson():
  with open(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "vocab_index.json"), "r") as indexfile:
    jsonIndex = json.load(indexfile)
  return jsonIndex

def loadSimpleIndex():
  if not os.path.isfile(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "vocab_index.txt")):
    return []
  with open(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "vocab_index.txt"), "r") as indexfile:
    lines = [line.rstrip() for line in indexfile]
  return lines

def writeSimpleIndex(index):
  with open(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "vocab_index.txt"), "w") as indexfile: 
    print("\n".join(index), file=indexfile)


def writeIndex(index):
  with open(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "vocab_index.tsv"), "w") as indexfile:
    writer = csv.writer(indexfile, delimiter="\t")
    writer.writerows(index)

def checkIfUriInIndex(uri, index):
  for i, uriObj in enumerate(index):
    if uriObj["vocab-uri"] == uri:
      return i
  return None

def writeIndexJson(index):
  with open(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "vocab_index.json"), "w+") as indexfile:
    json.dump(index, indexfile, indent=4, sort_keys=True)

def loadFalloutIndex():
  if not os.path.isfile(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "fallout_index.csv")):
    return []
  with open(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "fallout_index.csv"), "r") as csvfile:
    reader = csv.reader(csvfile)
    return [row for row in reader]

def writeFalloutIndex(index):
  with open(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "fallout_index.csv"), "w+") as csvfile: 
    writer = csv.writer(csvfile, delimiter=",")
    for row in index:
      writer.writerow(row)

def readCsvFile(pathToFile):
  with open(pathToFile, "r") as csvfile:
    reader = csv.reader(csvfile)
    return set([row[0] for row in reader])

def readTsvFile(pathToFile):
  with open(pathToFile, "r") as csvfile:
    reader = csv.reader(csvfile, delimiter="\t")
    return set([row[1] for row in reader])

def loadListFile(pathToFile):
  with open(pathToFile, "r") as listFile:
    lines = [line.strip() for line in listFile]
  return lines


def inspectMetadata(rootdir):

  resultData = {"filenumber": 0}

  exptKeys = set(["triples", "E-Tag", "rapperErrors", "rapperWarnings", "lastModified", "content-length", "semantic-version", "NIR-header", "resource-header", "accessed"])

  for groupdir in [dir for dir in os.listdir(rootdir) if os.path.isdir(os.path.join(rootdir, dir))]:
    for artifactDir in [dir for dir in os.listdir(os.path.join(rootdir, groupdir)) if os.path.isdir(os.path.join(rootdir, groupdir, dir))]:
      print("Generating metadata for", groupdir, artifactDir, file=sys.stderr)
      versionDirs = [dir for dir in os.listdir(os.path.join(rootdir, groupdir, artifactDir)) if os.path.isdir(os.path.join(rootdir, groupdir, artifactDir, dir)) and dir != "target"]
      if versionDirs == []:
        print("Couldnt find version for", groupdir, artifactDir, file=sys.stderr)
        continue
      versionDir = versionDirs[0]  
      #filepath = os.path.join(rootdir, groupdir, artifactDir, versionDir, artifactDir + "_type=parsed.ttl")
      jsonPath = os.path.join(rootdir, groupdir, artifactDir, versionDir, artifactDir + "_type=meta.json")
      if not os.path.isfile(jsonPath):
        print("Couldnt find metadata", file=sys.stderr)
        continue
      resultData["filenumber"] += 1 
      with open(jsonPath, "r") as jsonFile:
        metadata = json.load(jsonFile)

      for key in set(metadata.keys()) - exptKeys:
        if key in resultData.keys():
          if str(metadata[key]) in resultData[key].keys():
            oldNumber = resultData[key][str(metadata[key])]
            resultData[key][str(metadata[key])] = oldNumber + 1
          else:
            resultData[key][str(metadata[key])] = 1
        else:
          resultData[key] = {str(metadata[key]) : 1}
  print(json.dumps(resultData, indent=1))


def genStats(rootdir):
  index = loadIndexJson()
  
  exptKeys = set(["triples", "E-Tag", "rapperErrors", "rapperWarnings", "lastModified", "content-length", "semantic-version", "NIR-header", "resource-header", "accessed", "non-information-uri"])

  resultData = {}

  for indexUri in index.keys():
    groupId, artifact =  stringTools.generateGroupAndArtifactFromUri(indexUri)

    if not os.path.isdir(os.path.join(rootdir, groupId, artifact)):
      print("Couldnt find data for", indexUri, file=sys.stderr)
      continue
    versionDirs = [dir for dir in os.listdir(os.path.join(rootdir, groupId, artifact)) if os.path.isdir(os.path.join(rootdir, groupId, artifact, dir)) and dir != "target"]
    if versionDirs == []:
        print("Couldnt find version for", groupId, artifact, file=sys.stderr)
        continue
    versionDir = versionDirs[0] 
    jsonPath = os.path.join(rootdir, groupId, artifact, versionDir, artifact + "_type=meta.json")
    if not os.path.isfile(jsonPath):
      print("Couldnt find metadata", file=sys.stderr)
      continue
    lodeShaclReport = os.path.join(rootdir, groupId, artifact, versionDir, artifact + "_type=shaclReport_validates=lodeMetadata.ttl")
    if not os.path.isfile(lodeShaclReport):
      print("Couldnt find shacl report", file=sys.stderr)
      continue
    lodeShaclGraph = inspectVocabs.getGraphOfVocabFile(lodeShaclReport)
    with open(jsonPath, "r") as jsonFile:
      metadata = json.load(jsonFile)

    for key in set(metadata.keys()) - exptKeys:
      if key in resultData.keys():
        if str(metadata[key]) in resultData[key].keys():
          oldNumber = resultData[key][str(metadata[key])]
          resultData[key][str(metadata[key])] = oldNumber + 1
        else:
          resultData[key][str(metadata[key])] = 1
      else:
        resultData[key] = {str(metadata[key]) : 1}
    
    lodeValue = inspectVocabs.checkShaclReport(lodeShaclGraph)
    if "lodeShaclValue" in resultData:
      if lodeValue in resultData["lodeShaclValue"]:
        oldNumber = resultData["lodeShaclValue"][lodeValue]
        resultData["lodeShaclValue"][lodeValue] = oldNumber +1
      else:
        resultData["lodeShaclValue"][lodeValue] = 1
    else:
      resultData["lodeShaclValue"] = {lodeValue : 1}

  print(json.dumps(resultData, indent=1))
     
    
